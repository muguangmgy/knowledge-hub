from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.common.audit import clear_actor_id, register_audit_listeners
from app.common.config import get_settings


class Base(DeclarativeBase):
    """ORM 声明基类。"""

    pass


settings = get_settings()
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # 取出连接前探活，降低 MySQL 断连导致的首请求失败
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
register_audit_listeners()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖用：请求结束关闭 Session（Phase 2+ 路由使用）。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        clear_actor_id()
        db.close()


def ping_mysql() -> None:
    """启动 / health 探活；失败则抛异常。"""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
