import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.models.rbac import Menu, RoleMenu
from app.services.menu_tree import build_menu_tree, is_builtin_menu, load_all_menus, menu_to_node

logger = logging.getLogger(__name__)

ALLOWED_TYPES = frozenset({"catalog", "menu", "button"})
ALLOWED_FLAG = frozenset({0, 1})  # visible / status


def get_menu_tree(db: Session) -> list[dict]:
    """全量菜单树（含隐藏/禁用，供管理端）。"""
    menus = load_all_menus(db)
    # 管理端树：不过滤 status/visible，直接组树
    return build_menu_tree(menus)


def _validate_menu_fields(
    *,
    type_: str | None = None,
    visible: int | None = None,
    status: int | None = None,
) -> None:
    """校验 type / visible / status 枚举；非法 → 40001。"""
    if type_ is not None and type_ not in ALLOWED_TYPES:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的菜单类型", http_status=400)
    if visible is not None and visible not in ALLOWED_FLAG:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的 visible", http_status=400)
    if status is not None and status not in ALLOWED_FLAG:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的 status", http_status=400)


def create_menu(
    db: Session,
    *,
    parent_id: int = 0,
    name: str,
    path: str | None = None,
    icon: str | None = None,
    type_: str,
    perms: str | None = None,
    sort: int = 0,
    visible: int = 1,
    status: int = 1,
) -> dict:
    """新建菜单节点；父节点须存在（parent_id=0 为根）。"""
    name = name.strip()
    if not name:
        raise AppError(ErrorCode.BAD_REQUEST, "菜单名称不能为空", http_status=400)
    _validate_menu_fields(type_=type_, visible=visible, status=status)
    if parent_id:
        parent = db.get(Menu, parent_id)
        if parent is None:
            raise AppError(ErrorCode.NOT_FOUND, "父菜单不存在", http_status=404)

    menu = Menu(
        parent_id=parent_id or 0,
        name=name,
        path=path,
        icon=icon,
        type=type_,
        perms=perms,
        sort=sort,
        visible=visible,
        status=status,
    )
    db.add(menu)
    db.commit()
    db.refresh(menu)
    logger.info(event_msg("menu.create_ok", menu_id=menu.id, name=menu.name))
    return menu_to_node(menu)


def update_menu(
    db: Session,
    *,
    menu_id: int,
    parent_id: int | None = None,
    name: str | None = None,
    path: str | None = None,
    icon: str | None = None,
    type_: str | None = None,
    perms: str | None = None,
    sort: int | None = None,
    visible: int | None = None,
    status: int | None = None,
) -> dict:
    """更新菜单字段；禁止 parent 指向自己。"""
    menu = db.get(Menu, menu_id)
    if menu is None:
        raise AppError(ErrorCode.NOT_FOUND, "菜单不存在", http_status=404)
    _validate_menu_fields(type_=type_, visible=visible, status=status)

    if parent_id is not None:
        if parent_id == menu_id:
            raise AppError(ErrorCode.BAD_REQUEST, "父菜单不能是自己", http_status=400)
        if parent_id:
            parent = db.get(Menu, parent_id)
            if parent is None:
                raise AppError(ErrorCode.NOT_FOUND, "父菜单不存在", http_status=404)
        menu.parent_id = parent_id
    if name is not None:
        name = name.strip()
        if not name:
            raise AppError(ErrorCode.BAD_REQUEST, "菜单名称不能为空", http_status=400)
        menu.name = name
    if path is not None:
        menu.path = path
    if icon is not None:
        menu.icon = icon
    if type_ is not None:
        menu.type = type_
    if perms is not None:
        menu.perms = perms
    if sort is not None:
        menu.sort = sort
    if visible is not None:
        menu.visible = visible
    if status is not None:
        menu.status = status

    db.commit()
    db.refresh(menu)
    logger.info(event_msg("menu.update_ok", menu_id=menu.id))
    return menu_to_node(menu)


def delete_menu(db: Session, menu_id: int) -> None:
    """删除菜单；内置节点 / 仍有子节点 → 40001；并清理 role_menu。"""
    menu = db.get(Menu, menu_id)
    if menu is None:
        raise AppError(ErrorCode.NOT_FOUND, "菜单不存在", http_status=404)
    if is_builtin_menu(menu):
        raise AppError(ErrorCode.BAD_REQUEST, "不能删除内置系统管理菜单", http_status=400)
    child_count = db.scalar(
        select(func.count()).select_from(Menu).where(Menu.parent_id == menu_id)
    )
    if child_count:
        raise AppError(ErrorCode.BAD_REQUEST, "请先删除子菜单", http_status=400)
    db.execute(delete(RoleMenu).where(RoleMenu.menu_id == menu_id))
    db.delete(menu)
    db.commit()
    logger.info(event_msg("menu.delete_ok", menu_id=menu_id))
