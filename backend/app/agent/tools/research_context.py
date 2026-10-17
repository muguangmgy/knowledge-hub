"""会话标的槽：Redis 读写，失败降级为无上一只。"""

from __future__ import annotations

import json
import logging

from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)

_KEY_TMPL = "kh:agent:research_ctx:{conversation_id}"
_TTL_SEC = 2 * 60 * 60


def _key(conversation_id: int) -> str:
    """会话标的槽的 Redis key。"""
    return _KEY_TMPL.format(conversation_id=conversation_id)


def _client():
    """取 Redis；未配置时打 WARNING 并返回 None。"""
    from app.common.redis_client import get_redis

    client = get_redis()
    if client is None:
        logger.warning(event_msg("research.context_unavailable", reason="no_redis"))
    return client


def get_research_context(conversation_id: int | None) -> dict | None:
    """读取上一只标的；成功读之后续期。无槽或失败返回 None。"""
    if not conversation_id:
        return None
    client = _client()
    if client is None:
        return None
    key = _key(int(conversation_id))
    try:
        raw = client.get(key)
    except Exception as exc:
        logger.warning(event_msg("research.context_unavailable", op="get", err=exc))
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception as exc:
        logger.warning(event_msg("research.context_unavailable", op="parse", err=exc))
        return None
    if not isinstance(data, dict):
        return None
    code = str(data.get("code") or "").strip()
    name = str(data.get("name") or "").strip()
    if not code or not name:
        return None
    try:
        client.expire(key, _TTL_SEC)
    except Exception as exc:
        logger.warning(event_msg("research.context_unavailable", op="expire", err=exc))
    return {"code": code, "name": name}


def set_research_context(
    conversation_id: int | None,
    *,
    code: str | None = None,
    name: str | None = None,
    asset_code: str | None = None,
    asset_name: str | None = None,
) -> None:
    """写入标的槽并设置 2 小时 TTL；失败只打 WARNING。"""
    if not conversation_id:
        return
    # 调用方有的传 code/name，有的直接传 intent 里的 asset_code/asset_name
    code_s = str(code or asset_code or "").strip()
    name_s = str(name or asset_name or "").strip()
    if not code_s or not name_s:
        return
    client = _client()
    if client is None:
        return
    key = _key(int(conversation_id))
    payload = json.dumps({"code": code_s, "name": name_s}, ensure_ascii=False)
    try:
        client.set(key, payload)
        client.expire(key, _TTL_SEC)
    except Exception as exc:
        logger.warning(event_msg("research.context_unavailable", op="set", err=exc))


def delete_research_context(conversation_id: int | None) -> None:
    """删除标的槽；失败只打 WARNING。"""
    if not conversation_id:
        return
    client = _client()
    if client is None:
        return
    try:
        client.delete(_key(int(conversation_id)))
    except Exception as exc:
        logger.warning(event_msg("research.context_unavailable", op="delete", err=exc))
