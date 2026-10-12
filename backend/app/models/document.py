"""文档元数据 kh_document：全员共享库，无 user_id / status；有行即入库成功。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Document(Base):
    """共享库文档元数据。"""

    __tablename__ = "kh_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # 全库唯一；同名拒绝上传（Phase 3）
    filename: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
