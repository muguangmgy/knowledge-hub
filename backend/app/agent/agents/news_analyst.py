from __future__ import annotations

from app.agent.logging_util import check_deadline
from app.agent.tools.tencent import fetch_tencent_news


def news_analyst_node(state: dict) -> dict:
    """拉取腾讯个股资讯（最多 6 条），写入 news。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return patch

    intent = state.get("intent") or {}
    code = intent.get("asset_code")
    if not code:
        return {"news": None, "errors": ["news_analyst: missing asset_code"]}

    try:
        items = fetch_tencent_news(code=str(code), limit=6, news_type=1)
        return {"news": items, "errors": []}
    except Exception as exc:
        return {"news": None, "errors": [f"news_fetch_failed: {exc}"]}
