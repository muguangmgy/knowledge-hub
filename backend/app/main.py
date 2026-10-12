"""FastAPI 入口：CORS、lifespan、health、auth、documents、chat（Phase1–4）。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.auth.seed import run_seed
from app.common.chroma import open_chroma
from app.common.config import get_settings
from app.common.db import Base, SessionLocal, engine, ping_mysql
from app.common.errors import AppError, ErrorCode
from app.common.response import fail, ok
import app.models  # noqa: F401  # 导入以注册 ORM 元数据，供 create_all


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动顺序：探活 MySQL → 建表 → 幂等种子 → 打开 Chroma。任一步失败则进程起不来。"""
    settings = get_settings()
    settings.kb_dir.mkdir(parents=True, exist_ok=True)

    ping_mysql()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        run_seed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    open_chroma(settings)
    yield


app = FastAPI(title="Knowledge Hub", lifespan=lifespan)

settings = get_settings()
# Token 走 Bearer Header，不依赖 Cookie，故 allow_credentials=False
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request, exc: AppError):
    """将 AppError 转为统一 JSON 失败响应。"""
    return fail(exc.code, exc.message, exc.http_status)


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/api/health")
def health():
    """探活 MySQL 与已初始化的 Chroma；无需登录。"""
    try:
        ping_mysql()
    except Exception:
        return fail(ErrorCode.INTERNAL, "MySQL unavailable", http_status=503)

    try:
        from app.common.chroma import get_chroma

        get_chroma().list_collections()
    except Exception:
        return fail(ErrorCode.INTERNAL, "Chroma unavailable", http_status=503)

    return ok({"mysql": "ok", "chroma": "ok"})
