"""会话与问答业务：懒建会话 → 检索 → 拒答或 LLM 生成。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user import User
from app.rag.retriever import retrieve
from app.services import qa


def list_conversations(db: Session, user: User) -> list[dict]:
    """仅当前用户的会话，按更新时间倒序。"""
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [_conv_to_dict(c) for c in rows]


def get_conversation_messages(db: Session, user: User, conversation_id: int) -> dict:
    """消息详情；非本人 → 40401。"""
    conv = _get_owned_conversation(db, user, conversation_id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.asc())
    ).all()
    return {
        "conversation": _conv_to_dict(conv),
        "messages": [_msg_to_dict(m) for m in messages],
    }


def delete_conversation(db: Session, user: User, conversation_id: int) -> None:
    """删除会话及其消息；非本人 → 40401。"""
    conv = _get_owned_conversation(db, user, conversation_id)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conv.id)
    ).all()
    for m in messages:
        db.delete(m)
    db.delete(conv)
    db.commit()


def ask(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
) -> dict:
    """主问答入口。

    - conversationId 缺省则懒建；已传则校验归属
    - 空结果或 Top-1 distance 过大 → rejected=true，不调 LLM
    - LLM 失败：保留 user 消息并写失败说明 assistant，再抛 50010
    """
    settings = get_settings()
    question = (message or "").strip()
    if not question:
        raise AppError(ErrorCode.INTERNAL, "消息不能为空", http_status=400)

    if conversation_id is None:
        conv = Conversation(user_id=user.id, title=question[:40])
        db.add(conv)
        db.flush()
    else:
        conv = _get_owned_conversation(db, user, conversation_id)
        if not conv.title:
            conv.title = question[:40]

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=question,
        citations=None,
    )
    db.add(user_msg)
    db.flush()

    # 生成侧：当前消息之前最近 6 条；检索仍只用当前问题原文
    history_rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.id < user_msg.id)
        .order_by(Message.id.desc())
        .limit(6)
    ).all()
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_rows)
        if m.role in {"user", "assistant"}
    ]

    try:
        chunks = retrieve(question)
    except AppError as exc:
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise

    rejected = False
    citations: list[dict] = []
    if not chunks or chunks[0].distance > settings.RAG_REJECT_MAX_DISTANCE:
        rejected = True
        answer = qa.REJECT_REPLY
    else:
        doc_ids = {c.document_id for c in chunks}
        titles: dict[int, str] = {}
        if doc_ids:
            docs = db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
            titles = {d.id: d.title for d in docs}
        citations = qa.build_citations(chunks, titles=titles)
        try:
            answer = qa.generate_answer(
                question=question,
                chunks=chunks,
                history=history,
                titles=titles,
            )
        except AppError:
            # 保留 user 消息，写失败说明 assistant
            fail_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content="生成答案失败，请稍后重试。",
                citations=None,
            )
            db.add(fail_msg)
            db.commit()
            raise

    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=citations or None,
    )
    db.add(assistant)
    conv.updated_at = datetime.now()
    db.commit()

    return {
        "conversationId": conv.id,
        "answer": answer,
        "rejected": rejected,
        "citations": citations,
        "messageId": assistant.id,
    }


def _get_owned_conversation(
    db: Session, user: User, conversation_id: int
) -> Conversation:
    """校验会话归属当前用户；否则 40401。"""
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise AppError(ErrorCode.NOT_FOUND, "会话不存在", http_status=404)
    return conv


def _conv_to_dict(c: Conversation) -> dict:
    """会话 ORM → API camelCase。"""
    return {
        "id": c.id,
        "title": c.title,
        "createdAt": c.created_at.isoformat() if c.created_at else None,
        "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
    }


def _msg_to_dict(m: Message) -> dict:
    """消息 ORM → API camelCase。"""
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": m.citations,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }
