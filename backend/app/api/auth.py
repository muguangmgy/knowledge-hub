from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户，默认绑定角色 user。"""
    user = auth_service.register_user(
        db, username=body.username, password=body.password
    )
    return ok(
        {
            "id": user.id,
            "username": user.username,
            "status": user.status,
        }
    )


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """登录成功返回 accessToken。"""
    data = auth_service.login_user(db, username=body.username, password=body.password)
    return ok(data)


@router.get("/me")
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户资料（含 roles / menus）。"""
    return ok(auth_service.get_user_profile(db, current_user))
