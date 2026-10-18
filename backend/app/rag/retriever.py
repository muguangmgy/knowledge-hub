from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.rag import bm25_store
from app.rag.chroma_store import get_or_create_collection
from app.rag.embedding import embed_texts

# RRF 常数；越大则排名差的影响越小
_RRF_K = 60

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """检索命中的一条切片，供 chat / qa 做拒答判定与引用生成。

    distance：Chroma cosine distance，越小越相似（0 最近，约 2 最远）。
    纯 BM25 命中无向量距离时，用占位 distance（偏大）标记来源。
    正式问答路径以精排分数门控为准，不再用本字段做二次拒答。
    """

    chroma_id: str  # 向量库 id，格式 {document_id}_{chunk_index}
    document_id: int
    chunk_id: int  # MySQL chunk.id
    filename: str
    heading_path: str  # Markdown 标题路径；无则为空
    content: str  # 切片原文，写入 prompt / citations.snippet
    distance: float


def filter_relevant(
    chunks: list[RetrievedChunk],
    *,
    relative: bool = True,
) -> list[RetrievedChunk]:
    """按向量距离做按条过滤（调试/无精排场景用）。

    正式 chat.ask 在 Rerank 分数门控后不再调用本函数：
    BM25 捞回的正确命中常有较大 cosine distance，绝对阈值会误杀。

    保留条件：
      1. 绝对：distance <= RAG_REJECT_MAX_DISTANCE（始终）
      2. 相对：若 relative=True，distance - top1 <= RAG_RELATIVE_MAX_GAP
    """
    if not chunks:
        return []

    settings = get_settings()
    max_distance = settings.RAG_REJECT_MAX_DISTANCE
    max_gap = settings.RAG_RELATIVE_MAX_GAP
    top1_distance = chunks[0].distance

    kept: list[RetrievedChunk] = []
    for c in chunks:
        if c.distance > max_distance:
            continue
        if relative and (c.distance - top1_distance) > max_gap:
            continue
        kept.append(c)
    return kept


def retrieve(query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
    """混合检索入口（由 chat.ask 调用，结果再交给 Rerank）。

    链路：
      1. 向量近邻（语义）与 BM25（关键词）各召回 path_k 条
      2. RRF 按排名融合去重，截断为 final_k（默认 = path_k，给精排更宽候选）
      3. 返回列表顺序 = RRF 分从高到低（尚未按问答相关性精排）
    """
    settings = get_settings()
    final_k = top_k or settings.RAG_HYBRID_PATH_TOP_K
    path_k = settings.RAG_HYBRID_PATH_TOP_K

    query = (query or "").strip()
    if not query:
        return []

    t0 = time.perf_counter()
    vector_hits = _retrieve_vector(query, top_k=path_k)
    bm25_hits = bm25_store.search(query, top_k=path_k)
    fused = _rrf_fuse(vector_hits, bm25_hits, final_k=final_k)
    logger.info(
        event_msg(
            "retrieve",
            vector_n=len(vector_hits),
            bm25_n=len(bm25_hits),
            fused_n=len(fused),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    return fused


def _retrieve_vector(query: str, *, top_k: int) -> list[RetrievedChunk]:
    """向量一路：query Embedding → Chroma cosine 近邻。

    错误：入库侧 INGEST_FAILED(50001) 抬成问答侧 LLM_FAILED(50010)。
    """
    try:
        vectors = embed_texts([query])
    except AppError as exc:
        if exc.code == ErrorCode.INGEST_FAILED:
            raise AppError(ErrorCode.LLM_FAILED, exc.message, http_status=500) from exc
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.LLM_FAILED, f"检索 Embedding 失败: {exc}", http_status=500
        ) from exc

    coll = get_or_create_collection()
    try:
        total = coll.count()
    except Exception:
        total = top_k
    n_results = max(1, min(top_k, total)) if total else top_k

    result = coll.query(
        query_embeddings=vectors,
        n_results=n_results,
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


def _rrf_fuse(
    vector_hits: list[RetrievedChunk],
    bm25_hits: list[bm25_store.Bm25Hit],
    *,
    final_k: int,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion：两路按排名 reciprocal 加权求和后截断。

    对每路第 rank 名（0-based）：
      向量贡献 1 / (RRF_K + rank + 1)
      BM25 贡献 RAG_RRF_BM25_WEIGHT / (RRF_K + rank + 1)
    同分文档累加两路贡献；最终按合分降序取 final_k。
    """
    settings = get_settings()
    bm25_weight = float(settings.RAG_RRF_BM25_WEIGHT or 1.0)
    if bm25_weight <= 0:
        bm25_weight = 1.0

    scores: dict[str, float] = {}
    payload: dict[str, RetrievedChunk] = {}

    for rank, c in enumerate(vector_hits):
        scores[c.chroma_id] = scores.get(c.chroma_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        payload[c.chroma_id] = c

    placeholder_distance = (
        vector_hits[0].distance if vector_hits else 0.35
    )
    for rank, hit in enumerate(bm25_hits):
        scores[hit.chroma_id] = scores.get(hit.chroma_id, 0.0) + bm25_weight / (
            _RRF_K + rank + 1
        )
        if hit.chroma_id not in payload:
            payload[hit.chroma_id] = RetrievedChunk(
                chroma_id=hit.chroma_id,
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                filename=hit.filename,
                heading_path=hit.heading_path,
                content=hit.content,
                distance=float(placeholder_distance),
            )

    ordered_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [payload[cid] for cid in ordered_ids[:final_k]]
