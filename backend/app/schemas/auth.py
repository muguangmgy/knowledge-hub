"""认证请求体（Phase 2）。"""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册入参。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    """登录入参。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
