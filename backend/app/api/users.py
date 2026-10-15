from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.system import UserCreateRequest, UserUpdateRequest
from app.services import user_admin as user_admin_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    username: str | None = None,
    status: int | None = Query(None, ge=0, le=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """用户分页列表。"""
    return ok(
        user_admin_service.list_users(
            db, page=page, page_size=pageSize, username=username, status=status
        )
    )


@router.post("")
def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """创建用户。"""
    return ok(
        user_admin_service.create_user(
            db,
            username=body.username,
            password=body.password,
            role_ids=body.roleIds,
            status=body.status,
        )
    )


@router.get("/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """用户详情。"""
    return ok(user_admin_service.get_user(db, user_id))


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新用户状态 / 角色 / 密码。"""
    return ok(
        user_admin_service.update_user(
            db,
            actor_id=current_user.id,
            user_id=user_id,
            status=body.status,
            role_ids=body.roleIds,
            password=body.password,
        )
    )


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除用户。"""
    user_admin_service.delete_user(db, actor_id=current_user.id, user_id=user_id)
    return ok({})
