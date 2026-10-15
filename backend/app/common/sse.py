from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: dict[str, Any] | None = None) -> str:
    """组装业务 SSE 帧（``event:`` + JSON ``data:`` + 空行）。"""
    payload = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def format_sse_ping() -> str:
    """组装 SSE comment 心跳（``: ping``）；非业务事件，前端可忽略。"""
    return ": ping\n\n"
