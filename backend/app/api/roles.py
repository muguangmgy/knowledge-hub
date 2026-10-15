from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.system import RoleCreateRequest, RoleUpdateRequest
from app.services import role_admin as role_admin_service

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("")
def list_roles(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """角色列表。"""
    return ok(role_admin_service.list_roles(db))


@router.post("")
def create_role(
    body: RoleCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """创建角色。"""
    return ok(
        role_admin_service.create_role(
            db, code=body.code, name=body.name, menu_ids=body.menuIds
        )
    )


@router.get("/{role_id}")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """角色详情。"""
    return ok(role_admin_service.get_role(db, role_id))


@router.patch("/{role_id}")
def update_role(
    role_id: int,
    body: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """更新角色名称 / 菜单。"""
    return ok(
        role_admin_service.update_role(
            db, role_id=role_id, name=body.name, menu_ids=body.menuIds
        )
    )


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """删除角色（内置 admin/user 不可删）。"""
    role_admin_service.delete_role(db, role_id)
    return ok({})
