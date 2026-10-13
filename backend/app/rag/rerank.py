from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_n: int | None = None,
    titles: dict[int, str] | None = None,
) -> list[RetrievedChunk]:
    """SiliconFlow Rerank：按「问题–片段」相关性重排，取前 top_n。

    送入文本为「标题 | 小节 | 正文」，便于短词命中文档标题。
    分数门控（相对落差为主）：
      1. score >= RAG_RERANK_MIN_SCORE（软地板）
      2. score >= top1_score * RAG_RERANK_RELATIVE_RATIO（相对落差）
      3. 滤完为空且 top1 >= RAG_RERANK_KEEP_TOP1_FLOOR → 至少保留 Top1
    """
    if not chunks:
        return []

    query = (query or "").strip()
    if not query:
        return chunks

    settings = get_settings()
    n = top_n if top_n is not None else settings.RAG_TOP_K
    n = max(1, min(n, len(chunks)))
    min_score = settings.RAG_RERANK_MIN_SCORE
    relative_ratio = settings.RAG_RERANK_RELATIVE_RATIO
    keep_top1_floor = settings.RAG_RERANK_KEEP_TOP1_FLOOR
    titles = titles or {}

    api_key = (settings.RERANK_API_KEY or settings.EMBEDDING_API_KEY or "").strip()
    if not api_key:
        raise AppError(
            ErrorCode.LLM_FAILED,
            "未配置 RERANK_API_KEY / EMBEDDING_API_KEY",
            http_status=500,
        )

    base = (settings.RERANK_BASE_URL or settings.EMBEDDING_BASE_URL).rstrip("/")
    url = f"{base}/rerank"
    documents = [
        _doc_text(
            titles.get(c.document_id) or c.filename,
            c.heading_path,
            c.content,
        )
        for c in chunks
    ]
    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": n,
        "return_documents": False,
    }

    logger.info(
        "[精排·请求] 模型=%s 候选数=%s 截断top_n=%s 软地板=%s "
        "相对比例=%s Top1兜底地板=%s 问题=%r 候选ids=%s",
        settings.RERANK_MODEL,
        len(chunks),
        n,
        min_score,
        relative_ratio,
        keep_top1_floor,
        query,
        [c.chroma_id for c in chunks],
    )

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except AppError:
        raise
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise AppError(
            ErrorCode.LLM_FAILED,
            f"Rerank 失败: HTTP {exc.code} {detail}",
            http_status=500,
        ) from exc
    except Exception as exc:
        raise AppError(
            ErrorCode.LLM_FAILED, f"Rerank 失败: {exc}", http_status=500
        ) from exc

    results = data.get("results") or []
    # API 一般已按分数降序；再排一次保证 Top1 可靠
    parsed: list[tuple[RetrievedChunk, float]] = []
    for item in results:
        idx = int(item.get("index", -1))
        if idx < 0 or idx >= len(chunks):
            continue
        score = float(item.get("relevance_score") or 0.0)
        parsed.append((chunks[idx], score))
    parsed.sort(key=lambda x: x[1], reverse=True)

    ranked, scores, dropped = _apply_score_gate(
        parsed,
        min_score=min_score,
        relative_ratio=relative_ratio,
        keep_top1_floor=keep_top1_floor,
    )

    logger.info(
        "[精排·结果] 输出条数=%s 软地板=%s 相对比例=%s Top1兜底地板=%s "
        "丢弃=%s ids=%s 相关性分数=%s 距离=%s",
        len(ranked),
        min_score,
        relative_ratio,
        keep_top1_floor,
        [(cid, round(s, 4), reason) for cid, s, reason in dropped],
        [c.chroma_id for c in ranked],
        [round(s, 4) for s in scores],
        [round(c.distance, 4) for c in ranked],
    )
    return ranked


def _apply_score_gate(
    parsed: list[tuple[RetrievedChunk, float]],
    *,
    min_score: float,
    relative_ratio: float,
    keep_top1_floor: float,
) -> tuple[list[RetrievedChunk], list[float], list[tuple[str, float, str]]]:
    """精排分数门控：绝对软地板 + 相对落差；空则按地板兜底 Top1。"""
    if not parsed:
        return [], [], []

    top1_score = parsed[0][1]
    relative_cut = top1_score * relative_ratio
    ranked: list[RetrievedChunk] = []
    scores: list[float] = []
    dropped: list[tuple[str, float, str]] = []

    for chunk, score in parsed:
        cid = chunk.chroma_id
        if score < min_score:
            dropped.append((cid, score, "abs"))
            continue
        if score < relative_cut:
            dropped.append((cid, score, "rel"))
            continue
        ranked.append(chunk)
        scores.append(score)

    # 滤完为空：Top1 尚可接受则至少保留，避免短问误拒答
    if not ranked and parsed[0][1] >= keep_top1_floor:
        top_chunk, top_score = parsed[0]
        ranked = [top_chunk]
        scores = [top_score]
        dropped = [
            (cid, s, reason)
            for cid, s, reason in dropped
            if cid != top_chunk.chroma_id
        ]
        logger.info(
            "[精排·Top1兜底] 保留 id=%s score=%s floor=%s",
            top_chunk.chroma_id,
            round(top_score, 4),
            keep_top1_floor,
        )

    return ranked, scores, dropped


def _doc_text(title: str, heading_path: str, content: str) -> str:
    """拼精排输入：标题优先，便于关键词短问命中。"""
    parts = [p for p in [(title or "").strip(), (heading_path or "").strip()] if p]
    head = " | ".join(parts)
    body = (content or "").strip()
    if head and body:
        return f"{head}\n{body}"
    return head or body
