from __future__ import annotations

import logging
from typing import Any


def setup_app_logging() -> None:
    """挂载 app 根 logger，使 app.* 的 INFO 出现在控制台。"""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


def event_msg(event: str, **fields: Any) -> str:
    """拼一条规范业务日志：event=... k=v ..."""
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").replace("\r", "").strip()
        if " " in text or "=" in text:
            text = text.replace(" ", "_").replace("=", "_")
        parts.append(f"{key}={text}")
    return " ".join(parts)
