"""轻投研短答：依据快照与财务，不套研报模板，不发信。"""

from __future__ import annotations

import json
from collections.abc import Iterator

from app.agent.logging_util import check_deadline
from app.llm.client import chat_completion, chat_completion_stream

LIGHT_TIMEOUT_MSG = "查询超时，请稍后重试。"
LIGHT_EMPTY_MSG = "行情与财务数据暂不可用，请稍后再试。"
LIGHT_DISCLAIMER = "仅供参考，不构成投资建议。"
EMAIL_HINT = "发送邮件需要走研报流程（例如：分析某某并生成研报发到邮箱）。"

_SYSTEM = (
    "你是投研助手。根据给出的行情快照与财务要点，用简短 Markdown 直接回答当前问题。"
    "禁止写成研报，不要使用章节式标题或研报模板。"
    "禁止编造数据里没有的数字。不要自己写免责声明。"
)


def _has_quote(quote: object) -> bool:
    """快照里有概览正文，或现价字段不是空。"""
    if not isinstance(quote, dict):
        return False
    if quote.get("core_overview_md") or quote.get("core_overview"):
        return True
    spot = quote.get("spot")
    return isinstance(spot, dict) and spot.get("price") is not None


def _has_finance(finance: object) -> bool:
    """财务要点里至少有一个报告期。"""
    if not isinstance(finance, dict):
        return False
    periods = finance.get("periods")
    return isinstance(periods, list) and len(periods) > 0


def _quote_for_prompt(quote: object) -> dict | None:
    """只把短答要用的现价字段放进 prompt。"""
    if not isinstance(quote, dict):
        return None
    spot = quote.get("spot") if isinstance(quote.get("spot"), dict) else {}
    return {
        "name": quote.get("name") or spot.get("name"),
        "code": quote.get("code") or spot.get("code"),
        "price": spot.get("price"),
        "change_pct": spot.get("change_pct"),
        "change_amount": spot.get("change_amount"),
        "pe_dynamic": spot.get("pe_dynamic"),
        "pb": spot.get("pb"),
        "market_cap_yi": spot.get("market_cap_yi"),
        "core_overview_md": quote.get("core_overview_md"),
    }


def build_light_messages(state: dict) -> list[dict[str, str]]:
    """短答 prompt：当前问题 + 快照/财务，不拼闲聊历史。"""
    intent = state.get("intent") or {}
    payload = {
        "question": state.get("user_input") or "",
        "asset_name": intent.get("asset_name"),
        "asset_code": intent.get("asset_code"),
        "quote_data": _quote_for_prompt(state.get("quote_data")),
        "finance_data": state.get("finance_data"),
        "errors": state.get("errors") or [],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]


def finalize_light_body(body: str, *, want_email: bool) -> str:
    """补上免责声明；有发信意图时追加研报流程提示。"""
    text = (body or "").strip() or LIGHT_EMPTY_MSG
    if "不构成投资建议" not in text:
        text = f"{text.rstrip()}\n\n{LIGHT_DISCLAIMER}"
    if want_email and "发送邮件需要走研报流程" not in text:
        text = f"{text.rstrip()}\n\n{EMAIL_HINT}"
    return text


def light_answer_node(state: dict) -> dict:
    """同步短答；超时或全空数据走硬编码，不调用 Mailer。"""
    return {"report_md": light_answer_sync_text(state)}


def iter_light_deltas(state: dict) -> Iterator[str]:
    """流式短答增量；免责声明与发信提示在末尾一次补上。"""
    yield from _compose_chunks(state)


def _compose_chunks(state: dict) -> Iterator[str]:
    """超时或双空走硬编码；否则流式补全，文末只再推尚未出现的收口。"""
    patch = check_deadline(state)
    if state.get("timed_out") or patch.get("timed_out"):
        yield LIGHT_TIMEOUT_MSG
        return

    intent = state.get("intent") or {}
    want_email = bool(intent.get("want_email"))
    quote = state.get("quote_data")
    finance = state.get("finance_data")
    if not _has_quote(quote) and not _has_finance(finance):
        yield finalize_light_body(LIGHT_EMPTY_MSG, want_email=want_email)
        return

    messages = build_light_messages(state)
    parts: list[str] = []
    for chunk in chat_completion_stream(messages):
        parts.append(chunk)
        yield chunk
    final = finalize_light_body("".join(parts), want_email=want_email)
    raw = "".join(parts)
    # 免责声明和发信提示已经作为增量推过正文，这里只补差额
    if final.startswith(raw):
        suffix = final[len(raw) :]
        if suffix:
            yield suffix
    elif final != raw:
        yield final


def light_answer_sync_text(state: dict) -> str:
    """同步路径：一次补全后做同样的文末收口。"""
    patch = check_deadline(state)
    if state.get("timed_out") or patch.get("timed_out"):
        return LIGHT_TIMEOUT_MSG
    intent = state.get("intent") or {}
    want_email = bool(intent.get("want_email"))
    if not _has_quote(state.get("quote_data")) and not _has_finance(state.get("finance_data")):
        return finalize_light_body(LIGHT_EMPTY_MSG, want_email=want_email)
    raw = chat_completion(build_light_messages(state))
    return finalize_light_body(raw, want_email=want_email)
