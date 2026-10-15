from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.system import MenuCreateRequest, MenuUpdateRequest
from app.services import menu_admin as menu_admin_service

router = APIRouter(prefix="/api/menus", tags=["menus"])


@router.get("/tree")
def menu_tree(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """全量菜单树。"""
    return ok(menu_admin_service.get_menu_tree(db))


@router.post("")
def create_menu(
    body: MenuCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """新建菜单节点。"""
    return ok(
        menu_admin_service.create_menu(
            db,
            parent_id=body.parentId,
            name=body.name,
            path=body.path,
            icon=body.icon,
            type_=body.type,
            perms=body.perms,
            sort=body.sort,
            visible=body.visible,
            status=body.status,
        )
    )


@router.patch("/{menu_id}")
def update_menu(
    menu_id: int,
    body: MenuUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """更新菜单。"""
    return ok(
        menu_admin_service.update_menu(
            db,
            menu_id=menu_id,
            parent_id=body.parentId,
            name=body.name,
            path=body.path,
            icon=body.icon,
            type_=body.type,
            perms=body.perms,
            sort=body.sort,
            visible=body.visible,
            status=body.status,
        )
    )


@router.delete("/{menu_id}")
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """删除菜单（内置系统管理不可删；有子节点拒绝）。"""
    menu_admin_service.delete_menu(db, menu_id)
    return ok({})
