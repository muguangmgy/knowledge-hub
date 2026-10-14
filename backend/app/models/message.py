from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Message(Base):
    """会话消息；assistant 可带 citations JSON。"""

    __tablename__ = "message"
    __table_args__ = {"comment": "会话消息表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="消息ID"
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属会话ID（conversation.id）",
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="角色：user / assistant / system",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息正文"
    )
    citations: Mapped[list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="引用片段 JSON（assistant 用；含 doc_id/chunk_id/snippet 等）",
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
