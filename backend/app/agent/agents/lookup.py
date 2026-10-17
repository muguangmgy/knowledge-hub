"""轻投研拉数：腾讯快照 + 财务要点，不拉日 K 与资讯。"""

from __future__ import annotations

from app.agent.logging_util import check_deadline
from app.agent.tools.finance import build_finance_bundle
from app.agent.tools.tencent import build_quote_bundle


def lookup_node(state: dict) -> dict:
    """为 LightAnswer 准备 quote_data / finance_data；失败写入 errors。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return patch

    intent = state.get("intent") or {}
    code = intent.get("asset_code")
    if not code:
        return {
            "quote_data": None,
            "finance_data": None,
            "errors": ["lookup: missing asset_code"],
        }

    errors: list[str] = []
    quote_data = None
    try:
        quote_data = build_quote_bundle(str(code))
    except Exception as exc:
        errors.append(f"quote_fetch_failed: {exc}")

    # 快照已到手但截止已过：留下行情，不再拉财务
    if check_deadline(state).get("timed_out"):
        return {"timed_out": True, "quote_data": quote_data, "errors": errors}

    finance_data = None
    try:
        finance_data = build_finance_bundle(str(code))
    except Exception as exc:
        errors.append(f"finance_fetch_failed: {exc}")

    return {
        "quote_data": quote_data,
        "finance_data": finance_data,
        "errors": errors,
    }
