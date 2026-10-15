import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.common.audit import actor_scope
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services.menu_tree import menus_for_user

logger = logging.getLogger(__name__)


def register_user(db: Session, *, username: str, password: str) -> User:
    """注册并默认绑定角色 user；用户名冲突 → 40902。"""
    username = username.strip()
    if not username or not password:
        raise AppError(ErrorCode.BAD_CREDENTIALS, "用户名或密码不能为空", http_status=400)

    exists = db.scalar(select(User).where(User.username == username))
    if exists is not None:
        raise AppError(ErrorCode.USERNAME_EXISTS, "用户名已存在", http_status=409)

    role = db.scalar(select(Role).where(Role.code == "user"))
    if role is None:
        raise AppError(ErrorCode.INTERNAL, "角色 user 未初始化", http_status=500)

    user = User(
        username=username,
        password_hash=hash_password(password),
        status=1,
    )
    db.add(user)
    db.flush()
    with actor_scope(user.id):
        user.created_by = user.id
        user.updated_by = user.id
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
    db.refresh(user)
    logger.info(event_msg("auth.register_ok", user_id=user.id, username=user.username))
    return user


def login_user(db: Session, *, username: str, password: str) -> dict:
    """校验密码且 status=1 后签发 JWT；错误凭证统一 40102。"""
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(ErrorCode.BAD_CREDENTIALS, "用户名或密码错误", http_status=401)
    if user.status != 1:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户已禁用", http_status=401)

    token = create_access_token(user_id=user.id, username=user.username)
    logger.info(event_msg("auth.login_ok", user_id=user.id, username=user.username))
    return {
        "accessToken": token,
        "tokenType": "Bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "status": user.status,
        },
    }


def get_user_profile(db: Session, user: User) -> dict:
    """聚合 roles + menus 树，供 GET /me（无 permissions）。"""
    role_rows = db.execute(
        select(Role.id, Role.code, Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    ).all()
    # 去重保序：按 code 排序
    seen: set[str] = set()
    roles: list[dict] = []
    for _rid, code, name in sorted(role_rows, key=lambda r: r[1]):
        if code in seen:
            continue
        seen.add(code)
        roles.append({"code": code, "name": name})

    return {
        "id": user.id,
        "username": user.username,
        "status": user.status,
        "roles": roles,
        "menus": menus_for_user(db, user.id),
    }
