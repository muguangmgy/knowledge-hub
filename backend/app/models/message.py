"""消息 kh_message；citations 仅存短摘录字段（Phase 4）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Message(Base):
    """会话消息；assistant 可带 citations JSON。"""

    __tablename__ = "kh_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
