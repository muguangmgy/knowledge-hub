from datetime import datetime

from sqlalchemy import BigInteger, DateTime, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class User(Base):
    """登录用户。"""

    __tablename__ = "sys_user"
    __table_args__ = {"comment": "用户表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="用户ID"
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="登录用户名（唯一）"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希（bcrypt）"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="账号状态：1=正常，0=禁用",
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id；种子可空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id；种子可空）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
