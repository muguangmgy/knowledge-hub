from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Conversation(Base):
    """用户会话（chat 懒建）；mode 区分 rag / direct，会话级锁定不可混聊。"""

    __tablename__ = "conversation"
    __table_args__ = {"comment": "对话会话表（按用户隔离）"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="会话ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属用户ID（sys_user.id）",
    )
    title: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="会话标题（可空；首条用户消息截断写入）",
    )
    mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="rag",
        server_default="rag",
        comment="会话模式：rag | direct",
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
