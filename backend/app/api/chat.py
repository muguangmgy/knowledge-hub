from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.chat import ChatRequest, ConversationUpdateRequest
from app.services import chat as chat_service

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
