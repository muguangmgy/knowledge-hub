from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import SessionLocal, get_db
from app.common.response import ok
from app.common.sse import format_sse, format_sse_ping
from app.models.user import User
from app.schemas.chat import ChatRequest, ConversationUpdateRequest
from app.services import chat as chat_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/api/chat")
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """统一问答入口：body.mode 为 rag（知识库）或 direct（自由对话）。"""
    data = chat_service.ask(
        db,
        user,
        message=body.message,
        conversation_id=body.conversationId,
        mode=body.mode,
    )
    return ok(data)


@router.post("/api/chat/stream")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE 流式问答；建流前校验失败走 AppError；响应为 text/event-stream。

    工作线程持独立 DB Session 跑 ask_stream；主协程按队列写出 SSE，
    并在客户端断开时 set cancel_event。
    """
    chat_service.validate_ask_preflight(
        db,
        user,
        message=body.message,
        conversation_id=body.conversationId,
        mode=body.mode,
    )

    cancel_event = threading.Event()
    event_q: queue.Queue[dict[str, Any] | None] = queue.Queue()
    user_id = user.id

    def worker() -> None:
        """在独立线程执行 ask_stream，事件写入 queue；结束放 None。"""
        work_db = SessionLocal()
        try:
            u = work_db.get(User, user_id)
            if u is None:
                event_q.put(
                    {
                        "event": "error",
                        "data": {"code": 40101, "message": "用户不存在或已禁用"},
                    }
                )
                return
            for ev in chat_service.ask_stream(
                work_db,
                u,
                message=body.message,
                conversation_id=body.conversationId,
                mode=body.mode,
                should_cancel=cancel_event.is_set,
            ):
                event_q.put(ev)
                if ev.get("event") in ("done", "error", "cancelled"):
                    return
        except Exception:
            logger.exception("chat.stream_failed user_id=%s", user_id)
            event_q.put(
                {
                    "event": "error",
                    "data": {"code": 50000, "message": "流式问答内部错误"},
                }
            )
        finally:
            work_db.close()
            event_q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_publisher():
        """从队列取事件并编码为 SSE 字节；感知断开以取消上游。"""
        while True:
            if await request.is_disconnected():
                cancel_event.set()
            try:
                ev = await asyncio.to_thread(event_q.get, True, 0.5)
            except queue.Empty:
                continue
            if ev is None:
                break
            et = ev.get("event")
            if et == "cancelled":
                break
            if et == "ping":
                yield format_sse_ping().encode("utf-8")
                continue
            if et == "_result":
                continue
            yield format_sse(et, ev.get("data")).encode("utf-8")
            if et in ("done", "error"):
                break
            if await request.is_disconnected():
                cancel_event.set()

    return StreamingResponse(
        event_publisher(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/conversations")
def list_conversations(
    mode: str | None = Query(
        default=None, description="rag | direct；缺省只返回 rag 会话"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户会话列表；按 mode 过滤（缺省等价 mode=rag）。"""
    return ok(chat_service.list_conversations(db, user, mode=mode))


@router.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """会话消息详情（仅本人）。"""
    return ok(chat_service.get_conversation_messages(db, user, conversation_id))


@router.patch("/api/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    body: ConversationUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新会话标题（仅本人）。"""
    return ok(
        chat_service.update_conversation_title(
            db, user, conversation_id, body.title
        )
    )


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除会话及其消息（仅本人）。"""
    chat_service.delete_conversation(db, user, conversation_id)
    return ok({})
