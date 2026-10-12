"""向量检索：当前问题原文 → Embedding → Chroma Top-K（cosine distance）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.rag.chroma_store import get_or_create_collection
from app.rag.embedding import embed_texts


@dataclass
class RetrievedChunk:
    """检索命中片段；distance 越小越近（cosine）。"""

    chroma_id: str
    document_id: int
    chunk_id: int
    filename: str
    heading_path: str
    content: str
    distance: float


def retrieve(query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
    """全库检索；问答阶段 Embedding 失败映射为 50010。"""
    settings = get_settings()
    k = top_k or settings.RAG_TOP_K
    query = (query or "").strip()
    if not query:
        return []

    try:
        vectors = embed_texts([query])
    except AppError as exc:
        # embed_texts 默认 INGEST_FAILED(50001)；问答侧统一抬成 LLM_FAILED(50010)
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.LLM_FAILED, f"检索 Embedding 失败: {exc}", http_status=500
        ) from exc

    coll = get_or_create_collection()
    result = coll.query(
        query_embeddings=vectors,
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    items: list[RetrievedChunk] = []
    for i, chroma_id in enumerate(ids):
        meta = metas[i] or {}
        items.append(
            RetrievedChunk(
                chroma_id=chroma_id,
                document_id=int(meta.get("document_id") or 0),
                chunk_id=int(meta.get("chunk_id") or 0),
                filename=str(meta.get("filename") or ""),
                heading_path=str(meta.get("heading_path") or ""),
                content=docs[i] or "",
                distance=float(dists[i]),
            )
        )
    return items
