from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import touch
from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user import User
from app.rag.rerank import rerank_chunks
from app.rag.retriever import retrieve
from app.services import qa

# 合法会话 / 请求 mode；与 conversation.mode、前端路由约定一致
CHAT_MODES = frozenset({"rag", "direct"})
DEFAULT_CHAT_MODE = "rag"


def normalize_chat_mode(mode: str | None) -> str:
    """规范化对话 mode：缺失或 null → rag；非空非法值抛 BAD_REQUEST(40001)。"""
    if mode is None:
        return DEFAULT_CHAT_MODE
    if not isinstance(mode, str):
        raise AppError(ErrorCode.BAD_REQUEST, "无效的对话模式", http_status=400)
    cleaned = mode.strip()
    if not cleaned:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的对话模式", http_status=400)
    if cleaned not in CHAT_MODES:
        raise AppError(ErrorCode.BAD_REQUEST, "无效的对话模式", http_status=400)
    return cleaned


def list_conversations(
    db: Session, user: User, *, mode: str | None = None
) -> list[dict]:
    """仅当前用户的会话，按更新时间倒序；mode 缺省按 rag 过滤。"""
    resolved = normalize_chat_mode(mode)
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.mode == resolved)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [_conv_to_dict(c) for c in rows]


def get_conversation_messages(db: Session, user: User, conversation_id: int) -> dict:
    """消息详情；非本人 → 40401。不按 mode 过滤。"""
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


def update_conversation_title(
    db: Session, user: User, conversation_id: int, title: str
) -> dict:
    """更新会话标题；非本人 → 40401。"""
    conv = _get_owned_conversation(db, user, conversation_id)
    conv.title = title[:512]
    touch(conv)
    db.commit()
    db.refresh(conv)
    return _conv_to_dict(conv)


def ask(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
    mode: str | None = None,
) -> dict:
    """主问答入口（由 POST /api/chat 调用）。

    1. 规范化 mode（缺省 rag）
    2. 懒建会话并写入 mode，或续聊时校验 mode 与会话一致（不一致不写消息）
    3. 落库 user 消息后按 mode 分支：
       - rag → _ask_rag（检索，生成不带历史）
       - direct → _ask_direct（不检索，带最近 6 条历史）
    """
    settings = get_settings()
    chat_mode = normalize_chat_mode(mode)

    question = (message or "").strip()
    if not question:
        raise AppError(ErrorCode.INTERNAL, "消息不能为空", http_status=400)

    # 懒建：写入 mode；续聊：mode 必须与会话一致
    if conversation_id is None:
        conv = Conversation(
            user_id=user.id,
            title=question[:40],
            mode=chat_mode,
        )
        db.add(conv)
        db.flush()
    else:
        conv = _get_owned_conversation(db, user, conversation_id)
        if conv.mode != chat_mode:
            raise AppError(
                ErrorCode.BAD_REQUEST,
                "会话模式不匹配，不允许混聊",
                http_status=400,
            )
        if not conv.title:
            conv.title = question[:40]
        touch(conv)

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=question,
        citations=None,
    )
    db.add(user_msg)
    db.flush()

    if chat_mode == "direct":
        return _ask_direct(db, conv, user_msg, question)

    return _ask_rag(db, settings, conv, user_msg, question)


def _ask_direct(
    db: Session,
    conv: Conversation,
    user_msg: Message,
    question: str,
) -> dict:
    """自由对话分支：取当前 user 消息之前最近 6 条历史，直调 LLM。

    不调用 retrieve / rerank；响应恒为 rejected=false、citations=[]。
    LLM 失败时保留 user 消息并写入失败说明 assistant，再抛出。
    """
    # Message.id < 当前条，避免把本轮问题重复拼进 history
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
        answer = qa.generate_direct_answer(question=question, history=history)
    except AppError:
        fail_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="生成答案失败，请稍后重试。",
            citations=None,
        )
        db.add(fail_msg)
        touch(conv)
        db.commit()
        raise

    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=None,
    )
    db.add(assistant)
    touch(conv)
    db.commit()
    return {
        "conversationId": conv.id,
        "answer": answer,
        "rejected": False,
        "citations": [],
        "messageId": assistant.id,
    }


def _ask_rag(
    db: Session,
    settings,
    conv: Conversation,
    user_msg: Message,
    question: str,
) -> dict:
    """知识库问答分支：retrieve → rerank → 拒答或带引用生成。

    故意不查询 / 不传入对话历史；仅用当前问题与精排片段。
    Embedding/检索失败抬为 50010；LLM 失败保留 user 并写失败说明。
    """
    try:
        fused_chunks = retrieve(question)
        fused_doc_ids = {c.document_id for c in fused_chunks}
        titles: dict[int, str] = {}
        if fused_doc_ids:
            docs = db.scalars(
                select(Document).where(Document.id.in_(fused_doc_ids))
            ).all()
            titles = {d.id: d.title for d in docs}
        ranked_chunks = rerank_chunks(
            question,
            fused_chunks,
            top_n=settings.RAG_TOP_K,
            titles=titles,
        )
    except AppError as exc:
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise

    chunks = ranked_chunks
    rejected = False
    citations: list[dict] = []
    if not chunks:
        rejected = True
        answer = qa.REJECT_REPLY
    else:
        doc_ids = {c.document_id for c in chunks}
        titles = {i: titles[i] for i in doc_ids if i in titles}
        citations = qa.build_citations(chunks, titles=titles)
        try:
            answer = qa.generate_answer(
                question=question,
                chunks=chunks,
                titles=titles,
            )
        except AppError:
            fail_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content="生成答案失败，请稍后重试。",
                citations=None,
            )
            db.add(fail_msg)
            touch(conv)
            db.commit()
            raise

    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=citations or None,
    )
    db.add(assistant)
    touch(conv)
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
        "mode": c.mode,
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
