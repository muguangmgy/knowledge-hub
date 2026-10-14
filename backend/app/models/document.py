from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Document(Base):
    """共享库文档元数据。"""

    __tablename__ = "document"
    __table_args__ = {"comment": "文档表（全员共享库）"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="文档ID"
    )
    title: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="文档标题"
    )
    filename: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
        comment="原始文件名（全库唯一）",
    )
    file_path: Mapped[str] = mapped_column(
        String(1024), nullable=False, comment="本地落盘相对路径"
    )
    file_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="文件类型：pdf / docx / md / txt"
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="文件大小（字节）"
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
