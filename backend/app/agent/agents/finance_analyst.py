from __future__ import annotations

import logging

from app.agent.logging_util import check_deadline
from app.agent.tools.finance import build_finance_bundle
from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)


def finance_analyst_node(state: dict) -> dict:
    """拉取 AKShare 财务指标，写入 finance_data（含 periods；表由 Writer 格式化）。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return patch

    intent = state.get("intent") or {}
    code = intent.get("asset_code")
    if not code:
        return {"finance_data": None, "errors": ["finance_analyst: missing asset_code"]}

    try:
        data = build_finance_bundle(str(code))
        return {"finance_data": data, "errors": []}
    except Exception as exc:
        # 与其它 Analyst 一致：不抛到图外，避免一侧失败拖垮并行扇出
        logger.warning(event_msg("finance_analyst_node", err=exc))
        return {"finance_data": None, "errors": [f"finance_fetch_failed: {exc}"]}
