from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.rag.retriever import RetrievedChunk


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
    parsed: list[tuple[RetrievedChunk, float]] = []
    for item in results:
        idx = int(item.get("index", -1))
        if idx < 0 or idx >= len(chunks):
            continue
        score = float(item.get("relevance_score") or 0.0)
        parsed.append((chunks[idx], score))
    parsed.sort(key=lambda x: x[1], reverse=True)

    ranked, _scores = _apply_score_gate(
        parsed,
        min_score=min_score,
        relative_ratio=relative_ratio,
        keep_top1_floor=keep_top1_floor,
    )
    return ranked


def _apply_score_gate(
    parsed: list[tuple[RetrievedChunk, float]],
    *,
    min_score: float,
    relative_ratio: float,
    keep_top1_floor: float,
) -> tuple[list[RetrievedChunk], list[float]]:
    """精排分数门控：绝对软地板 + 相对落差；空则按地板兜底 Top1。"""
    if not parsed:
        return [], []

    top1_score = parsed[0][1]
    relative_cut = top1_score * relative_ratio
    ranked: list[RetrievedChunk] = []
    scores: list[float] = []

    for chunk, score in parsed:
        if score < min_score:
            continue
        if score < relative_cut:
            continue
        ranked.append(chunk)
        scores.append(score)

    if not ranked and parsed[0][1] >= keep_top1_floor:
        top_chunk, top_score = parsed[0]
        ranked = [top_chunk]
        scores = [top_score]

    return ranked, scores


def _doc_text(title: str, heading_path: str, content: str) -> str:
    """拼精排输入：标题优先，便于关键词短问命中。"""
    parts = [p for p in [(title or "").strip(), (heading_path or "").strip()] if p]
    head = " | ".join(parts)
    body = (content or "").strip()
    if head and body:
        return f"{head}\n{body}"
    return head or body
