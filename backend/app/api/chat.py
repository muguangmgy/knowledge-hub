from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service

router = APIRouter(tags=["chat"])


@router.post("/api/chat")
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """检索后拒答或生成带引用答案。"""
    data = chat_service.ask(
        db,
        user,
        message=body.message,
        conversation_id=body.conversationId,
    )
    return ok(data)


@router.get("/api/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户会话列表。"""
    return ok(chat_service.list_conversations(db, user))


@router.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """会话消息详情（仅本人）。"""
    return ok(chat_service.get_conversation_messages(db, user, conversation_id))


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除会话及其消息（仅本人）。"""
    chat_service.delete_conversation(db, user, conversation_id)
    return ok({})
