"""闲聊档：投研助手人设 + 最近 6 条历史，不检索、不拉行情。"""

from __future__ import annotations

from collections.abc import Iterator

from app.agent.logging_util import check_deadline
from app.llm.client import chat_completion, chat_completion_stream

CHAT_TIMEOUT_MSG = "回复超时，请稍后重试。"

_SYSTEM = (
    "你是投研助手，与产品入口一致。你可以闲聊，也可以回答非股票问题。"
    "不要检索知识库，也不要假装已经读过用户的企业文档。"
    "若涉及买卖建议，用一句话说明不构成投资建议。"
    "本助手主要覆盖 A 股；标的不在覆盖范围时说明这一点，不要编造行情数字。"
)


def build_chat_messages(state: dict) -> list[dict[str, str]]:
    """system + 最多 6 条历史 + 本轮用户话；本轮若已在历史末尾则去重。"""
    user_input = (state.get("user_input") or "").strip()
    history = [
        item
        for item in (state.get("history_messages") or [])
        if isinstance(item, dict)
    ][-6:]
    # 调用方有时已把本轮 user 放进历史末尾，避免同一句出现两次
    if (
        history
        and history[-1].get("role") == "user"
        and str(history[-1].get("content") or "").strip() == user_input
    ):
        history = history[:-1]

    system = _SYSTEM
    # 续指落空，或标的不在 A 股代码表时，改写 system，避免编造行情
    intent = state.get("intent") or {}
    if intent.get("clarify_previous"):
        system += "当前没有可沿用的股票。请向用户澄清你指哪只股票，不要编造行情数字。"
    uncovered = intent.get("uncovered_name")
    if uncovered:
        system += (
            f"用户提到的「{uncovered}」对不上 A 股代码表。"
            "请说明主要覆盖 A 股，不要编造行情数字。"
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in history:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_input})
    return messages


def chat_node(state: dict) -> dict:
    """同步闲聊补全；超时写短文案。"""
    patch = check_deadline(state)
    if state.get("timed_out") or patch.get("timed_out"):
        return {"report_md": CHAT_TIMEOUT_MSG}
    return {"report_md": (chat_completion(build_chat_messages(state)) or "").strip()}


def iter_chat_deltas(state: dict) -> Iterator[str]:
    """流式闲聊增量。"""
    patch = check_deadline(state)
    if state.get("timed_out") or patch.get("timed_out"):
        yield CHAT_TIMEOUT_MSG
        return
    yield from chat_completion_stream(build_chat_messages(state))
