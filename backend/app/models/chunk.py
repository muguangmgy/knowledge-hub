from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Chunk(Base):
    """文档切片；chroma_id 关联向量库。"""

    __tablename__ = "chunk"
    __table_args__ = {"comment": "文档切片表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="切片ID"
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="所属文档ID（document.id）",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="文档内切片序号（从 0 起）"
    )
    heading_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        default="",
        comment="标题路径（如 章 > 节）",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="切片正文"
    )
    chroma_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        comment="Chroma 向量ID，格式 {document_id}_{chunk_index}",
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
