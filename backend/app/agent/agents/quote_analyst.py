from __future__ import annotations

from app.agent.logging_util import check_deadline
from app.agent.tools.tencent import build_quote_bundle


def quote_analyst_node(state: dict) -> dict:
    """拉取腾讯快照，写入 quote_data（含核心概览 Markdown 表）。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return patch

    intent = state.get("intent") or {}
    code = intent.get("asset_code")
    if not code:
        return {"quote_data": None, "errors": ["quote_analyst: missing asset_code"]}

    try:
        data = build_quote_bundle(str(code))
        return {"quote_data": data, "errors": []}
    except Exception as exc:
        return {"quote_data": None, "errors": [f"quote_fetch_failed: {exc}"]}
