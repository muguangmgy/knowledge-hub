from __future__ import annotations

import logging
from functools import lru_cache

from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)

_client = None


@lru_cache
def get_redis():
    """按 REDIS_URL 创建客户端；未配置或连不上返回 None（调用方降级）。"""
    from app.common.config import get_settings

    url = (get_settings().REDIS_URL or "").strip()
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        client.ping()
        return client
    except Exception as exc:
        logger.warning(event_msg("get_redis", err=exc))
        return None


def reset_redis_client() -> None:
    """测试用：清掉缓存的客户端。"""
    global _client
    get_redis.cache_clear()
    _client = None
