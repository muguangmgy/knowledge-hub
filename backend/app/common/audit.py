from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.orm import Session

# 当前请求/任务的操作人；由 get_current_user 或 seed/register 显式设置
_actor_id: ContextVar[int | None] = ContextVar("audit_actor_id", default=None)


def get_actor_id() -> int | None:
    """读取当前请求绑定的操作人 user_id。"""
    return _actor_id.get()


def set_actor_id(user_id: int | None) -> None:
    """绑定当前操作人（如鉴权通过后）。"""
    _actor_id.set(user_id)


def clear_actor_id() -> None:
    """清除当前操作人 ContextVar。"""
    _actor_id.set(None)


@contextmanager
def actor_scope(user_id: int | None) -> Iterator[None]:
    """临时指定操作人（种子 / 注册自指等）。"""
    token = _actor_id.set(user_id)
    try:
        yield
    finally:
        _actor_id.reset(token)


def touch(obj) -> None:
    """标记对象被更新：推进 updated_at，flush 时由监听器补 updated_by。

    用于「只挂了子表、父行本身字段未改」但仍要刷新父行活跃时间的场景（如会话问答）。
    """
    if hasattr(obj, "updated_at"):
        obj.updated_at = datetime.now()


def _has_col(obj, name: str) -> bool:
    """判断 ORM 对象是否映射了指定列。"""
    mapper = getattr(type(obj), "__mapper__", None)
    if mapper is None:
        return False
    return name in mapper.columns


def _apply_insert(obj, actor: int) -> None:
    """插入时补 created_by / updated_by（仅空值）。"""
    if _has_col(obj, "created_by") and getattr(obj, "created_by", None) is None:
        obj.created_by = actor
    if _has_col(obj, "updated_by") and getattr(obj, "updated_by", None) is None:
        obj.updated_by = actor


def _apply_update(obj, actor: int) -> None:
    """更新时推进 updated_by。"""
    if _has_col(obj, "updated_by"):
        obj.updated_by = actor


def _before_flush(session: Session, _flush_context, _instances) -> None:
    """Session before_flush：按当前 actor 补审计字段。"""
    actor = get_actor_id()
    if actor is None:
        return
    for obj in session.new:
        _apply_insert(obj, actor)
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            _apply_update(obj, actor)


def register_audit_listeners() -> None:
    """挂到 Session：insert 补 created_by/updated_by；update 补 updated_by。"""
    # 避免重复注册（热重载）
    if getattr(register_audit_listeners, "_done", False):
        return
    event.listen(Session, "before_flush", _before_flush)
    register_audit_listeners._done = True  # type: ignore[attr-defined]
