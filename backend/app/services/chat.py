from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import touch
from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user import User
from app.rag.rerank import rerank_chunks
from app.rag.retriever import retrieve
from app.services import qa

logger = logging.getLogger(__name__)

# 合法会话 / 请求 mode；与 conversation.mode、前端路由约定一致
CHAT_MODES = frozenset({"rag", "direct"})
DEFAULT_CHAT_MODE = "rag"
_FAIL_REPLY = "生成答案失败，请稍后重试。"


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
    mode = conv.mode
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conv.id)
    ).all()
    for m in messages:
        db.delete(m)
    db.delete(conv)
    db.commit()
    from app.agent.tools.research_context import delete_research_context

    delete_research_context(conversation_id)
    logger.info(
        event_msg(
            "delete_conversation",
            user_id=user.id,
            conversation_id=conversation_id,
            mode=mode,
        )
    )


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
       - direct → _ask_direct（投研三档路由，不检索）
    """
    settings = get_settings()
    chat_mode, question, conv, user_msg = _prepare_ask(
        db, user, message=message, conversation_id=conversation_id, mode=mode
    )

    if chat_mode == "direct":
        return _ask_direct(db, user, conv, question, user_msg)

    return _ask_rag(db, user, settings, conv, question)


def validate_ask_preflight(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
    mode: str | None = None,
) -> str:
    """建流前校验（不写库）；返回规范化 mode。失败抛 AppError。"""
    chat_mode = normalize_chat_mode(mode)
    question = (message or "").strip()
    if not question:
        raise AppError(ErrorCode.INTERNAL, "消息不能为空", http_status=400)
    if conversation_id is not None:
        conv = _get_owned_conversation(db, user, conversation_id)
        if conv.mode != chat_mode:
            raise AppError(
                ErrorCode.BAD_REQUEST,
                "会话模式不匹配，不允许混聊",
                http_status=400,
            )
    return chat_mode


def ask_stream(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
    mode: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """SSE 问答入口（由 POST /api/chat/stream 调用）。

    先 commit user 再推 meta；按 mode 分支 rag/direct。
    yield 形如 ``{"event": "...", "data": {...}}``；
    event 含 meta/stage/citations/delta/done/error/ping/cancelled。
    should_cancel 为真时尽快停止；不落半成品 assistant。
    """
    cancel = should_cancel or (lambda: False)
    settings = get_settings()
    chat_mode, question, conv, user_msg = _prepare_ask(
        db, user, message=message, conversation_id=conversation_id, mode=mode
    )
    # 流式：先 commit user，再推 meta（§6）
    db.commit()
    yield {
        "event": "meta",
        "data": {"conversationId": conv.id, "mode": chat_mode},
    }
    if cancel():
        yield {"event": "cancelled"}
        return

    if chat_mode == "direct":
        yield from _ask_direct_stream(db, user, conv, question, user_msg, cancel)
        return

    yield from _ask_rag_stream(db, user, settings, conv, question, cancel)


def _prepare_ask(
    db: Session,
    user: User,
    *,
    message: str,
    conversation_id: int | None,
    mode: str | None,
) -> tuple[str, str, Conversation, Message]:
    """规范化 mode、懒建/校验会话、写入 user 消息（flush，未 commit）。"""
    chat_mode = normalize_chat_mode(mode)
    question = (message or "").strip()
    if not question:
        raise AppError(ErrorCode.INTERNAL, "消息不能为空", http_status=400)

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
    return chat_mode, question, conv, user_msg


# 闲聊档带入模型的最近消息条数；轻投研与重投研不用这段历史
_DIRECT_HISTORY_LIMIT = 6


def _recent_direct_history(
    db: Session, conversation_id: int, exclude_message_id: int
) -> list[dict[str, str]]:
    """本会话最近最多 6 条 user/assistant，排除本轮 user，按 id 升序。"""
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.id != exclude_message_id)
            .where(Message.role.in_(("user", "assistant")))
            .order_by(Message.id.desc())
            .limit(_DIRECT_HISTORY_LIMIT)
        ).all()
    )
    rows.reverse()
    return [{"role": row.role, "content": row.content} for row in rows]


def _ask_direct(
    db: Session,
    user: User,
    conv: Conversation,
    question: str,
    user_msg: Message,
) -> dict:
    """投研三档分支。

    调用 run_research_graph，并传入会话 id 与最近 6 条（仅 chat 档使用）。
    不检索；rejected=false、citations=[]。
    Writer LLM 等致命失败时保留 user 并写失败说明后抛出。
    """
    from app.agent import run_research_graph

    history = _recent_direct_history(db, conv.id, user_msg.id)
    t0 = time.perf_counter()
    try:
        result = run_research_graph(
            question,
            conversation_id=conv.id,
            history_messages=history,
        )
        answer = result["report_md"]
    except AppError:
        _commit_fail_assistant(db, conv)
        logger.warning(
            event_msg(
                "_ask_direct",
                mode="direct",
                user_id=user.id,
                conversation_id=conv.id,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        raise

    assistant = _commit_assistant(db, conv, answer, citations=None)
    logger.info(
        event_msg(
            "_ask_direct",
            mode="direct",
            route=result.get("route") or "-",
            user_id=user.id,
            conversation_id=conv.id,
            message_id=assistant.id,
            timed_out=bool(result.get("timed_out")),
            delivery=result.get("delivery_status") or "-",
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    return {
        "conversationId": conv.id,
        "answer": answer,
        "rejected": False,
        "citations": [],
        "messageId": assistant.id,
    }


def _ask_direct_stream(
    db: Session,
    user: User,
    conv: Conversation,
    question: str,
    user_msg: Message,
    cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """投研 SSE 分支：转发 iter_research_stream 的 stage/delta/ping。

    final → 落库 assistant 并转为 done；LLM 失败落库失败文案后 done（不抛）。
    取消则 cancelled，不落库、不发信。历史仅 chat 档使用。
    """
    from app.agent.stream import iter_research_stream

    history = _recent_direct_history(db, conv.id, user_msg.id)
    t0 = time.perf_counter()
    try:
        for ev in iter_research_stream(
            question,
            conversation_id=conv.id,
            history_messages=history,
            should_cancel=cancel,
        ):
            et = ev.get("event")
            if et == "cancelled":
                yield ev
                return
            if et == "ping":
                yield ev
                continue
            if et == "final":
                result = ev.get("data") or {}
                answer = result.get("report_md") or ""
                assistant = _commit_assistant(db, conv, answer, citations=None)
                logger.info(
                    event_msg(
                        "_ask_direct_stream",
                        mode="direct",
                        route=result.get("route") or "-",
                        user_id=user.id,
                        conversation_id=conv.id,
                        message_id=assistant.id,
                        timed_out=bool(result.get("timed_out")),
                        delivery=result.get("delivery_status") or "-",
                        elapsed_ms=int((time.perf_counter() - t0) * 1000),
                        stream=1,
                    )
                )
                yield {
                    "event": "done",
                    "data": {
                        "conversationId": conv.id,
                        "messageId": assistant.id,
                        "answer": answer,
                        "rejected": False,
                        "citations": [],
                        "timedOut": bool(result.get("timed_out")),
                        "deliveryStatus": result.get("delivery_status") or "",
                    },
                }
                return
            yield ev
    except AppError as exc:
        if cancel():
            yield {"event": "cancelled"}
            return
        assistant = _commit_fail_assistant(db, conv)
        logger.warning(
            event_msg(
                "_ask_direct_stream",
                mode="direct",
                user_id=user.id,
                conversation_id=conv.id,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                stream=1,
            )
        )
        yield {
            "event": "done",
            "data": {
                "conversationId": conv.id,
                "messageId": assistant.id,
                "answer": _FAIL_REPLY,
                "rejected": False,
                "citations": [],
                "timedOut": False,
                "deliveryStatus": "",
            },
        }
        # 同步路径会再 raise；流式用 done 收口，不再 raise
        _ = exc
        return


def _ask_rag(
    db: Session,
    user: User,
    settings,
    conv: Conversation,
    question: str,
) -> dict:
    """知识库问答分支：retrieve → rerank → 拒答或带引用生成。

    故意不查询 / 不传入对话历史；仅用当前问题与精排片段。
    Embedding/检索失败抬为 50010；LLM 失败保留 user 并写失败说明。
    """
    t0 = time.perf_counter()
    try:
        chunks, titles, citations = _retrieve_and_rank(db, settings, question)
    except AppError as exc:
        logger.warning(
            event_msg(
                "_ask_rag",
                mode="rag",
                user_id=user.id,
                conversation_id=conv.id,
                stage="retrieve",
                err=exc.message,
            )
        )
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise

    rejected = False
    if not chunks:
        rejected = True
        answer = qa.REJECT_REPLY
    else:
        try:
            answer = qa.generate_answer(
                question=question,
                chunks=chunks,
                titles=titles,
            )
        except AppError:
            _commit_fail_assistant(db, conv)
            logger.warning(
                event_msg(
                    "_ask_rag",
                    mode="rag",
                    user_id=user.id,
                    conversation_id=conv.id,
                    stage="generate",
                    elapsed_ms=int((time.perf_counter() - t0) * 1000),
                )
            )
            raise

    assistant = _commit_assistant(
        db, conv, answer, citations=citations or None
    )
    logger.info(
        event_msg(
            "_ask_rag",
            mode="rag",
            user_id=user.id,
            conversation_id=conv.id,
            message_id=assistant.id,
            rejected=rejected,
            citations=len(citations),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    return {
        "conversationId": conv.id,
        "answer": answer,
        "rejected": rejected,
        "citations": citations,
        "messageId": assistant.id,
    }


def _ask_rag_stream(
    db: Session,
    user: User,
    settings,
    conv: Conversation,
    question: str,
    cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """RAG SSE 分支：stage retrieving → 拒答或 citations + LLM delta → done。

    检索失败且未落库 → error；LLM 失败落库失败说明 → done。
    取消 → cancelled，不落半成品。
    """
    t0 = time.perf_counter()
    yield {
        "event": "stage",
        "data": {"stage": "retrieving", "message": "正在检索知识库…"},
    }
    if cancel():
        yield {"event": "cancelled"}
        return

    try:
        # 与 Session 同线程执行检索，避免 SQLAlchemy 跨线程
        chunks, titles, citations = _retrieve_and_rank(db, settings, question)
    except AppError as exc:
        logger.warning(
            event_msg(
                "_ask_rag_stream",
                mode="rag",
                user_id=user.id,
                conversation_id=conv.id,
                stage="retrieve",
                err=exc.message,
                stream=1,
            )
        )
        code = (
            ErrorCode.LLM_FAILED
            if exc.code == ErrorCode.INGEST_FAILED
            else exc.code
        )
        msg = exc.message
        yield {"event": "error", "data": {"code": code, "message": msg}}
        return

    if cancel():
        yield {"event": "cancelled"}
        return

    if not chunks:
        yield {"event": "delta", "data": {"text": qa.REJECT_REPLY}}
        assistant = _commit_assistant(
            db, conv, qa.REJECT_REPLY, citations=None
        )
        logger.info(
            event_msg(
                "_ask_rag_stream",
                mode="rag",
                user_id=user.id,
                conversation_id=conv.id,
                message_id=assistant.id,
                rejected=True,
                citations=0,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                stream=1,
            )
        )
        yield {
            "event": "done",
            "data": {
                "conversationId": conv.id,
                "messageId": assistant.id,
                "answer": qa.REJECT_REPLY,
                "rejected": True,
                "citations": [],
            },
        }
        return

    yield {"event": "citations", "data": {"citations": citations}}
    if cancel():
        yield {"event": "cancelled"}
        return

    parts: list[str] = []
    try:
        for piece in qa.generate_answer_stream(
            question=question, chunks=chunks, titles=titles
        ):
            if cancel():
                yield {"event": "cancelled"}
                return
            parts.append(piece)
            yield {"event": "delta", "data": {"text": piece}}
    except AppError:
        if cancel():
            yield {"event": "cancelled"}
            return
        assistant = _commit_fail_assistant(db, conv)
        logger.warning(
            event_msg(
                "_ask_rag_stream",
                mode="rag",
                user_id=user.id,
                conversation_id=conv.id,
                stage="generate",
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                stream=1,
            )
        )
        yield {
            "event": "done",
            "data": {
                "conversationId": conv.id,
                "messageId": assistant.id,
                "answer": _FAIL_REPLY,
                "rejected": False,
                "citations": citations,
            },
        }
        return

    answer = "".join(parts).strip()
    assistant = _commit_assistant(db, conv, answer, citations=citations or None)
    logger.info(
        event_msg(
            "_ask_rag_stream",
            mode="rag",
            user_id=user.id,
            conversation_id=conv.id,
            message_id=assistant.id,
            rejected=False,
            citations=len(citations),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            stream=1,
        )
    )
    yield {
        "event": "done",
        "data": {
            "conversationId": conv.id,
            "messageId": assistant.id,
            "answer": answer,
            "rejected": False,
            "citations": citations,
        },
    }


def _retrieve_and_rank(
    db: Session, settings, question: str
) -> tuple[list, dict[int, str], list[dict]]:
    """retrieve + rerank + citations；供同步/流式共用。"""
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
    if not ranked_chunks:
        return [], titles, []
    doc_ids = {c.document_id for c in ranked_chunks}
    titles = {i: titles[i] for i in doc_ids if i in titles}
    citations = qa.build_citations(ranked_chunks, titles=titles)
    return ranked_chunks, titles, citations


def _commit_assistant(
    db: Session,
    conv: Conversation,
    content: str,
    *,
    citations: list | None,
) -> Message:
    """写入 assistant 消息并 touch 会话；返回已 refresh 的行。"""
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=content,
        citations=citations,
    )
    db.add(assistant)
    touch(conv)
    db.commit()
    db.refresh(assistant)
    return assistant


def _commit_fail_assistant(db: Session, conv: Conversation) -> Message:
    """落库固定失败说明文案（与现网同步路径一致）。"""
    return _commit_assistant(db, conv, _FAIL_REPLY, citations=None)


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
