from __future__ import annotations

import time
from typing import Any


def check_deadline(state: dict[str, Any]) -> dict[str, Any]:
    """超时则返回 timed_out=True 补丁；未超时返回空 dict。"""
    if state.get("timed_out"):
        return {"timed_out": True}
    deadline = float(state.get("deadline_ts") or 0)
    if deadline and time.time() > deadline:
        return {"timed_out": True}
    return {}
