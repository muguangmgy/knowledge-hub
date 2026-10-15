from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.common.audit import set_actor_id
from app.common.db import get_db
from app.common.errors import AppError, ErrorCode
from app.models.user import User

# auto_error=False：缺 Token 时由我们返回统一业务码 40101，而非 FastAPI 默认 403
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer JWT 并确认用户 status=1；失败 → 40101。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(ErrorCode.UNAUTHORIZED, "未登录或 Token 无效", http_status=401)

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise AppError(
            ErrorCode.UNAUTHORIZED, "未登录或 Token 无效", http_status=401
        ) from exc

    # 必须再查库：禁用用户持旧 Token 也应 40101
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or user.status != 1:
        raise AppError(ErrorCode.UNAUTHORIZED, "未登录或 Token 无效", http_status=401)
    set_actor_id(user.id)  # flush 时自动填 created_by / updated_by
    return user
