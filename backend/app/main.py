"""FastAPI 应用入口：启动预热、中间件、全局异常、路由挂载与健康检查。"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.menus import router as menus_router
from app.api.roles import router as roles_router
from app.api.users import router as users_router
from app.auth.seed import run_seed
from app.common.chroma import open_chroma
from app.common.config import get_settings
from app.common.db import Base, SessionLocal, engine, ping_mysql
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg, setup_app_logging
from app.common.response import fail, ok
# 导入 models 才能把各表注册进 Base.metadata；否则 create_all 建不出表
import app.models  # noqa: F401

# 尽早挂日志，后面的启动步骤才能打到控制台
setup_app_logging()
logger = logging.getLogger(__name__)


def _elapsed_ms(started: float) -> int:
    """自 started（perf_counter）起经过的毫秒数。"""
    return int((time.perf_counter() - started) * 1000)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """进程启动时按顺序预热依赖，再对外提供服务。

    步骤：MySQL 探活 → 建表 → 种子 → Chroma → BM25 全量重建 → A 股代码表预热。
    前几步失败会让进程起不来；代码表预热失败只打 WARNING，不挡启动。
    各步成功日志 event 为步骤名并带 elapsed_ms；ready 带总耗时。
    yield 之后进入运行态；当前关闭阶段无额外清理。
    """
    settings = get_settings()
    boot_t0 = time.perf_counter()

    # 原文上传落盘目录（路径已锚定到 backend 根）
    settings.kb_dir.mkdir(parents=True, exist_ok=True)

    # MySQL 连不上则直接失败，避免半残状态接流量
    t0 = time.perf_counter()
    ping_mysql()
    logger.info(event_msg("mysql", elapsed_ms=_elapsed_ms(t0)))

    # 按 ORM 元数据补建缺失表；已有表不会做破坏性变更
    t0 = time.perf_counter()
    Base.metadata.create_all(bind=engine)
    logger.info(event_msg("db_schema", elapsed_ms=_elapsed_ms(t0)))

    # 幂等写入默认账号 / 角色 / 菜单等；失败回滚并阻止启动
    db = SessionLocal()
    try:
        t0 = time.perf_counter()
        run_seed(db)
        logger.info(event_msg("seed", elapsed_ms=_elapsed_ms(t0)))
    except Exception:
        db.rollback()
        logger.exception(event_msg("seed"))
        raise
    finally:
        db.close()

    # 向量库客户端；后续入库与 RAG 检索依赖这里初始化成功
    t0 = time.perf_counter()
    open_chroma(settings)
    logger.info(event_msg("chroma", elapsed_ms=_elapsed_ms(t0)))

    # BM25 关键词索引：每次启动从 MySQL 全量重建，与已入库切片对齐
    from app.rag import bm25_store

    bm25_db = SessionLocal()
    try:
        t0 = time.perf_counter()
        n = bm25_store.rebuild_from_db(bm25_db)
        logger.info(event_msg("bm25", chunks=n, elapsed_ms=_elapsed_ms(t0)))
    finally:
        bm25_db.close()

    # 投研用 A 股代码表：Redis → 本地 JSON → 新浪；失败可降级到首次解析时再拉
    try:
        from app.agent.tools.symbol import warm_symbol_cache

        t0 = time.perf_counter()
        rows = warm_symbol_cache()
        logger.info(event_msg("symbol_warm", rows=rows, elapsed_ms=_elapsed_ms(t0)))
    except Exception as exc:
        logger.warning(event_msg("symbol_warm", err=exc))

    logger.info(event_msg("ready", elapsed_ms=_elapsed_ms(boot_t0)))
    yield


app = FastAPI(title="Knowledge Hub", lifespan=lifespan)

settings = get_settings()
# Token 走 Authorization: Bearer，不依赖 Cookie，故 allow_credentials=False
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request, exc: AppError):
    """业务异常统一出口：AppError → 统一 fail JSON；其它未捕获异常仍走默认 500。"""
    return fail(exc.code, exc.message, exc.http_status)


# auth 登录注册；users/roles/menus 系统管理；documents 入库；chat 问答（含 SSE）
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(menus_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/api/health")
def health():
    """运维探活：MySQL + Chroma；无需登录。任一侧失败返回 503。

    不检查 Redis / BM25 / 新浪等可选依赖。
    """
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
