import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.models.rbac import Menu, Role, RoleMenu, UserRole

logger = logging.getLogger(__name__)

BUILTIN_ROLE_CODES = frozenset({"admin", "user"})
# 角色 code：字母开头，后接字母数字下划线
_CODE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")


def _role_menu_ids(db: Session, role_id: int) -> list[int]:
    """角色已绑菜单 id 列表。"""
    return list(
        db.scalars(select(RoleMenu.menu_id).where(RoleMenu.role_id == role_id)).all()
    )


def _serialize_role(db: Session, role: Role, *, with_menus: bool = False) -> dict:
    """角色 ORM → API camelCase；可选附带 menuIds。"""
    data = {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "createdAt": role.created_at.isoformat() if role.created_at else None,
        "updatedAt": role.updated_at.isoformat() if role.updated_at else None,
    }
    if with_menus:
        data["menuIds"] = _role_menu_ids(db, role.id)
    return data


def _replace_role_menus(db: Session, role_id: int, menu_ids: list[int]) -> None:
    """方案 A：请求给什么存什么，不自动写祖先。"""
    unique_ids = list(dict.fromkeys(menu_ids))
    if unique_ids:
        found = set(db.scalars(select(Menu.id).where(Menu.id.in_(unique_ids))).all())
        missing = set(unique_ids) - found
        if missing:
            raise AppError(ErrorCode.NOT_FOUND, "菜单不存在", http_status=404)
    db.execute(delete(RoleMenu).where(RoleMenu.role_id == role_id))
    for mid in unique_ids:
        db.add(RoleMenu(role_id=role_id, menu_id=mid))


def list_roles(db: Session) -> list[dict]:
    """角色列表（含 menuIds）。"""
    rows = db.scalars(select(Role).order_by(Role.id.asc())).all()
    return [_serialize_role(db, r, with_menus=True) for r in rows]


def get_role(db: Session, role_id: int) -> dict:
    """角色详情；不存在 → 40401。"""
    role = db.get(Role, role_id)
    if role is None:
        raise AppError(ErrorCode.NOT_FOUND, "角色不存在", http_status=404)
    return _serialize_role(db, role, with_menus=True)


def create_role(
    db: Session,
    *,
    code: str,
    name: str,
    menu_ids: list[int] | None = None,
) -> dict:
    """创建角色并绑定菜单；code 冲突 → 40903。"""
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise AppError(ErrorCode.BAD_REQUEST, "角色编码或名称不能为空", http_status=400)
    if not _CODE_RE.match(code):
        raise AppError(ErrorCode.BAD_REQUEST, "角色编码格式无效", http_status=400)
    if db.scalar(select(Role).where(Role.code == code)) is not None:
        raise AppError(ErrorCode.ROLE_EXISTS, "角色编码已存在", http_status=409)

    role = Role(code=code, name=name)
    db.add(role)
    db.flush()
    _replace_role_menus(db, role.id, menu_ids or [])
    db.commit()
    db.refresh(role)
    logger.info(event_msg("create_role", role_id=role.id, code=role.code))
    return _serialize_role(db, role, with_menus=True)


def update_role(
    db: Session,
    *,
    role_id: int,
    name: str | None = None,
    menu_ids: list[int] | None = None,
) -> dict:
    """更新角色名称与/或菜单绑定。"""
    role = db.get(Role, role_id)
    if role is None:
        raise AppError(ErrorCode.NOT_FOUND, "角色不存在", http_status=404)
    if name is not None:
        name = name.strip()
        if not name:
            raise AppError(ErrorCode.BAD_REQUEST, "角色名称不能为空", http_status=400)
        role.name = name
    if menu_ids is not None:
        _replace_role_menus(db, role.id, menu_ids)
    db.commit()
    db.refresh(role)
    logger.info(event_msg("update_role", role_id=role.id))
    return _serialize_role(db, role, with_menus=True)


def delete_role(db: Session, role_id: int) -> None:
    """删除角色及其 role_menu / user_role；内置角色拒绝。"""
    role = db.get(Role, role_id)
    if role is None:
        raise AppError(ErrorCode.NOT_FOUND, "角色不存在", http_status=404)
    if role.code in BUILTIN_ROLE_CODES:
        raise AppError(ErrorCode.BAD_REQUEST, "不能删除内置角色", http_status=400)
    db.execute(delete(RoleMenu).where(RoleMenu.role_id == role_id))
    db.execute(delete(UserRole).where(UserRole.role_id == role_id))
    db.delete(role)
    db.commit()
    logger.info(event_msg("delete_role", role_id=role_id))
