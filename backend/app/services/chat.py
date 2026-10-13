from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)


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
) -> dict:
    """主问答入口（由 api/chat.POST /api/chat 调用）。

    整体链路：
      1. 校验问题非空
      2. 懒建或加载会话（归属校验）
      3. 落库 user 消息
      4. 取最近历史（仅供 LLM，不参与检索）
      5. retrieve(question)
         → 向量 + BM25 双路召回 → RRF 融合
      6. rerank_chunks → 分数门控（相对落差 + 软地板 + Top1 兜底）
         → 为空 → 拒答；否则用精排结果生成（不再用向量距离二次砍杀）
      7. 落库 assistant 消息并 commit；返回 answer / rejected / citations

    失败约定：
      - Embedding/检索失败：业务码抬为 50010（LLM_FAILED）
      - LLM 失败：保留 user 消息，另写失败说明 assistant，再抛 50010
    """
    settings = get_settings()

    # --- 1. 入参校验 ---
    question = (message or "").strip()
    logger.info(
        "[问答·入参] user_id=%s username=%r conversation_id=%s 问题=%r "
        "精排保留条数=%s 各路召回条数=%s 精排模型=%s "
        "精排软地板=%s 精排相对比例=%s 精排Top1兜底=%s",
        user.id,
        user.username,
        conversation_id,
        question,
        settings.RAG_TOP_K,
        settings.RAG_HYBRID_PATH_TOP_K,
        settings.RERANK_MODEL,
        settings.RAG_RERANK_MIN_SCORE,
        settings.RAG_RERANK_RELATIVE_RATIO,
        settings.RAG_RERANK_KEEP_TOP1_FLOOR,
    )
    if not question:
        raise AppError(ErrorCode.INTERNAL, "消息不能为空", http_status=400)

    # --- 2. 会话：缺省懒建；已传则校验归属，必要时补标题 ---
    if conversation_id is None:
        # 新会话：title 暂用问题前 40 字
        conv = Conversation(user_id=user.id, title=question[:40])
        db.add(conv)
        db.flush()  # 拿到 conv.id，尚未 commit
        logger.info(
            "[问答·会话] 新建 id=%s title=%r", conv.id, conv.title
        )
    else:
        conv = _get_owned_conversation(db, user, conversation_id)
        if not conv.title:
            conv.title = question[:40]
        touch(conv)
        logger.info(
            "[问答·会话] 复用 id=%s title=%r", conv.id, conv.title
        )

    # --- 3. 先落库用户消息（失败路径也要保留提问）---
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=question,
        citations=None,
    )
    db.add(user_msg)
    db.flush()  # 拿到 user_msg.id，供历史截取排除本条
    logger.info(
        "[问答·用户消息] id=%s conversation_id=%s", user_msg.id, conv.id
    )

    # --- 4. 对话历史：当前消息之前最近 6 条，按时间正序交给 LLM ---
    # 检索仍只用当前问题原文，不把 history 拼进向量查询
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
    logger.info(
        "[问答·历史] 条数=%s roles=%s（仅进生成，不进检索）",
        len(history),
        [h["role"] for h in history],
    )

    # --- 5. 检索：双路召回 + RRF 融合 → Cross-Encoder 精排 ---
    # fused：候选较宽（默认 RAG_HYBRID_PATH_TOP_K）
    # ranked：精排截断为 RAG_TOP_K，顺序即最终引用 [n] 的候选序
    try:
        fused_chunks = retrieve(question)
        # 标题写入 rerank 文本，便于短词命中文档名（如「全栈开发」）
        fused_doc_ids = {c.document_id for c in fused_chunks}
        titles: dict[int, str] = {}
        if fused_doc_ids:
            docs = db.scalars(
                select(Document).where(Document.id.in_(fused_doc_ids))
            ).all()
            titles = {d.id: d.title for d in docs}
        logger.info(
            "[问答·精排前] 融合条数=%s 文档数=%s doc_ids=%s",
            len(fused_chunks),
            len(titles),
            sorted(fused_doc_ids),
        )
        ranked_chunks = rerank_chunks(
            question,
            fused_chunks,
            top_n=settings.RAG_TOP_K,
            titles=titles,
        )
    except AppError as exc:
        # embed_texts 默认抛 INGEST_FAILED(50001)；问答侧统一抬成 LLM_FAILED(50010)
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise

    # --- 6. 依据是否足够：以精排分数门控为准 → 拒答 或 带引用生成 ---
    # 不再对精排结果做向量距离二次过滤：BM25 捞回的正确命中可能 distance>阈值
    # （如「专业技能」→ 18_0 分数过门控但 distance≈0.57），会被误杀导致拒答。
    chunks = ranked_chunks
    rejected = False
    citations: list[dict] = []
    top1_distance = chunks[0].distance if chunks else None
    if not chunks:
        # 融合为空，或精排分数门控后无保留 → 规则拒答，不调 LLM
        rejected = True
        answer = qa.REJECT_REPLY
        logger.info(
            "[问答·拒答] 融合=%s 精排保留=%s top1距离=%s（已跳过向量距离门控）",
            len(fused_chunks),
            len(chunks),
            top1_distance,
        )
    else:
        # 仅用精排后片段：citations 与 prompt 同源、同序
        doc_ids = {c.document_id for c in chunks}
        titles = {i: titles[i] for i in doc_ids if i in titles}

        # index 从 1 起，与答案正文中的 [n] 对齐
        citations = qa.build_citations(chunks, titles=titles)

        logger.info(
            "[问答·生成前] 融合=%s 精排保留=%s top1距离=%s "
            "引用数=%s 历史条数=%s 保留ids=%s",
            len(fused_chunks),
            len(chunks),
            top1_distance,
            len(citations),
            len(history),
            [c.chroma_id for c in chunks],
        )
        try:
            # system + history + 当前问题与检索片段；一次非流式补全
            answer = qa.generate_answer(
                question=question,
                chunks=chunks,
                history=history,
                titles=titles,
            )
        except AppError:
            # 保留已写入的 user 消息；补一条失败说明 assistant，再向上抛 50010
            logger.exception(
                "[问答·LLM失败] conversation_id=%s user_message_id=%s",
                conv.id,
                user_msg.id,
            )
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

    # --- 7. 落库助手消息并提交整次问答事务 ---
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        citations=citations or None,  # 拒答时为空列表 → 存 NULL
    )
    db.add(assistant)
    touch(conv)
    db.commit()

    logger.info(
        "[问答·完成] conversation_id=%s message_id=%s 拒答=%s "
        "引用数=%s 答案长度=%s 引用ids=%s",
        conv.id,
        assistant.id,
        rejected,
        len(citations),
        len(answer or ""),
        [c.chroma_id for c in chunks] if chunks else [],
    )

    # 与前端约定的 camelCase 字段
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
