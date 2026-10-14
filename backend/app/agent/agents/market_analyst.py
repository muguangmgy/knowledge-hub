from __future__ import annotations

from app.agent.logging_util import check_deadline
from app.agent.tools.tencent import build_market_bundle


def market_analyst_node(state: dict) -> dict:
    """拉取腾讯日 K，写入 market_data（近 30 日走势 + 52 周高低）。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return patch

    intent = state.get("intent") or {}
    code = intent.get("asset_code")
    if not code:
        return {"market_data": None, "errors": ["market_analyst: missing asset_code"]}

    try:
        data = build_market_bundle(code=str(code))
        return {"market_data": data, "errors": []}
    except Exception as exc:
        return {"market_data": None, "errors": [f"market_fetch_failed: {exc}"]}
