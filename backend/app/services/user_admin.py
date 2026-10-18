import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.models.rbac import Role, UserRole
from app.models.user import User

logger = logging.getLogger(__name__)

ALLOWED_STATUS = frozenset({0, 1})  # 1=正常 / 0=禁用


def _user_role_ids(db: Session, user_id: int) -> list[int]:
    """用户已绑角色 id 列表。"""
    rows = db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id)).all()
    return list(rows)


def _serialize_user(db: Session, user: User) -> dict:
    """用户 ORM → API camelCase。"""
    return {
        "id": user.id,
        "username": user.username,
        "status": user.status,
        "roleIds": _user_role_ids(db, user.id),
        "createdAt": user.created_at.isoformat() if user.created_at else None,
        "updatedAt": user.updated_at.isoformat() if user.updated_at else None,
    }


def _replace_user_roles(db: Session, user_id: int, role_ids: list[int]) -> None:
    """全量替换用户角色绑定（先删后插）。"""
    unique_ids = list(dict.fromkeys(role_ids))
    if unique_ids:
        found = set(
            db.scalars(select(Role.id).where(Role.id.in_(unique_ids))).all()
        )
        missing = set(unique_ids) - found
        if missing:
            raise AppError(ErrorCode.NOT_FOUND, "角色不存在", http_status=404)
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for rid in unique_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))


def list_users(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    username: str | None = None,
    status: int | None = None,
) -> dict:
    """分页用户列表。"""
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    q = select(User)
    count_q = select(func.count()).select_from(User)
    if username:
        like = f"%{username.strip()}%"
        q = q.where(User.username.like(like))
        count_q = count_q.where(User.username.like(like))
    if status is not None:
        q = q.where(User.status == status)
        count_q = count_q.where(User.status == status)
    total = db.scalar(count_q) or 0
    rows = db.scalars(
        q.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_serialize_user(db, u) for u in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_user(db: Session, user_id: int) -> dict:
    """用户详情；不存在 → 40401。"""
    user = db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.NOT_FOUND, "用户不存在", http_status=404)
    return _serialize_user(db, user)


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role_ids: list[int] | None = None,
    status: int = 1,
) -> dict:
    """创建用户并绑定角色；用户名冲突 → 40902。"""
    username = username.strip()
    if not username or not password:
        raise AppError(ErrorCode.BAD_REQUEST, "用户名或密码不能为空", http_status=400)
    if status not in ALLOWED_STATUS:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的用户状态", http_status=400)
    if db.scalar(select(User).where(User.username == username)) is not None:
        raise AppError(ErrorCode.USERNAME_EXISTS, "用户名已存在", http_status=409)

    user = User(
        username=username,
        password_hash=hash_password(password),
        status=status,
    )
    db.add(user)
    db.flush()
    _replace_user_roles(db, user.id, role_ids or [])
    db.commit()
    db.refresh(user)
    logger.info(event_msg("create_user", user_id=user.id, username=user.username))
    return _serialize_user(db, user)


def update_user(
    db: Session,
    *,
    actor_id: int,
    user_id: int,
    status: int | None = None,
    role_ids: list[int] | None = None,
    password: str | None = None,
) -> dict:
    """更新状态 / 角色 / 密码；不能禁用自己。"""
    user = db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.NOT_FOUND, "用户不存在", http_status=404)

    if status is not None:
        if status not in ALLOWED_STATUS:
            raise AppError(ErrorCode.BAD_REQUEST, "无效的用户状态", http_status=400)
        # 防止操作者把自己禁用后无法再进系统
        if user_id == actor_id and status == 0:
            raise AppError(ErrorCode.BAD_REQUEST, "不能禁用当前登录用户", http_status=400)
        user.status = status

    if password is not None:
        if not password:
            raise AppError(ErrorCode.BAD_REQUEST, "密码不能为空", http_status=400)
        user.password_hash = hash_password(password)

    if role_ids is not None:
        _replace_user_roles(db, user.id, role_ids)

    db.commit()
    db.refresh(user)
    logger.info(event_msg("update_user", user_id=user.id))
    return _serialize_user(db, user)


def delete_user(db: Session, *, actor_id: int, user_id: int) -> None:
    """删除用户及其角色绑定；不能删自己。"""
    if user_id == actor_id:
        raise AppError(ErrorCode.BAD_REQUEST, "不能删除当前登录用户", http_status=400)
    user = db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.NOT_FOUND, "用户不存在", http_status=404)
    db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    db.delete(user)
    db.commit()
    logger.info(event_msg("delete_user", user_id=user_id))
