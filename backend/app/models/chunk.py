"""文档切片 kh_chunk；chroma_id 格式为 {document_id}_{chunk_index}。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Chunk(Base):
    """文档切片；chroma_id 关联向量库。"""

    __tablename__ = "kh_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chroma_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
