from __future__ import annotations

import logging
from dataclasses import dataclass

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.rag import bm25_store
from app.rag.chroma_store import COLLECTION_NAME, get_or_create_collection
from app.rag.embedding import embed_texts

logger = logging.getLogger(__name__)

# RRF 常数；越大则排名差的影响越小
_RRF_K = 60


@dataclass
class RetrievedChunk:
    """检索命中的一条切片，供 chat / qa 做拒答判定与引用生成。

    distance：Chroma cosine distance，越小越相似（0 最近，约 2 最远）。
    纯 BM25 命中无向量距离时，用占位 distance（偏大）标记来源。
    正式问答路径以精排分数门控为准，不再用本字段做二次拒答。
    """

    chroma_id: str  # 向量库 id，格式 {document_id}_{chunk_index}
    document_id: int
    chunk_id: int  # MySQL kh_chunk.id
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
    # 列表已按相关性排序时，[0] 视为当前最优（向量序或精排序）
    top1_distance = chunks[0].distance

    kept: list[RetrievedChunk] = []
    dropped: list[tuple[str, float, str]] = []  # (chroma_id, distance, reason)
    for c in chunks:
        # abs：整条过远，语义上不够近
        if c.distance > max_distance:
            dropped.append((c.chroma_id, c.distance, "abs"))
            continue
        # gap：相对 Top-1 差太多，多为擦边球（未精排时更有用）
        if relative and (c.distance - top1_distance) > max_gap:
            dropped.append((c.chroma_id, c.distance, "gap"))
            continue
        kept.append(c)

    logger.info(
        "[门控·按条过滤] 输入=%s 保留=%s top1距离=%s 启用相对gap=%s "
        "绝对阈值=%s 相对gap阈值=%s 丢弃=%s 保留ids=%s",
        len(chunks),
        len(kept),
        round(top1_distance, 4),
        relative,
        max_distance,
        max_gap,
        [(cid, round(d, 4), reason) for cid, d, reason in dropped],
        [c.chroma_id for c in kept],
    )
    return kept


def retrieve(query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
    """混合检索入口（由 chat.ask 调用，结果再交给 Rerank）。

    链路：
      1. 向量近邻（语义）与 BM25（关键词）各召回 path_k 条
      2. RRF 按排名融合去重，截断为 final_k（默认 = path_k，给精排更宽候选）
      3. 返回列表顺序 = RRF 分从高到低（尚未按问答相关性精排）
    """
    settings = get_settings()
    # 默认融合条数 = 各路召回条数，给 Rerank 更宽候选；也可显式传 top_k
    final_k = top_k or settings.RAG_HYBRID_PATH_TOP_K
    path_k = settings.RAG_HYBRID_PATH_TOP_K

    query = (query or "").strip()
    if not query:
        logger.info("[检索·跳过] 原因为空问题")
        return []

    logger.info(
        "[检索·开始] 问题=%r 各路召回条数=%s 融合截断=%s rrf_k=%s",
        query,
        path_k,
        final_k,
        _RRF_K,
    )

    # --- 双路召回：语义一路 + 关键词一路 ---
    vector_hits = _retrieve_vector(query, top_k=path_k)
    bm25_hits = bm25_store.search(query, top_k=path_k)

    # --- 融合：不比较绝对分数，只合并排名贡献 ---
    fused = _rrf_fuse(vector_hits, bm25_hits, final_k=final_k)
    logger.info(
        "[检索·混合完成] 问题=%r 各路召回=%s 向量命中=%s BM25命中=%s "
        "融合后=%s ids=%s 距离=%s",
        query,
        path_k,
        len(vector_hits),
        len(bm25_hits),
        len(fused),
        [c.chroma_id for c in fused],
        [round(c.distance, 4) for c in fused],
    )
    return fused


def _retrieve_vector(query: str, *, top_k: int) -> list[RetrievedChunk]:
    """向量一路：query Embedding → Chroma cosine 近邻。

    错误：入库侧 INGEST_FAILED(50001) 抬成问答侧 LLM_FAILED(50010)。
    """
    settings = get_settings()

    logger.info(
        "[检索·向量·入参] 问题=%r 请求条数=%s collection=%s "
        "embedding模型=%s 空间=cosine",
        query,
        top_k,
        COLLECTION_NAME,
        settings.EMBEDDING_MODEL,
    )

    # 与入库同一 Embedding 模型，保证同向量空间可比
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

    emb_dim = len(vectors[0]) if vectors and vectors[0] else 0
    logger.info(
        "[检索·向量·Embedding完成] batch=%s 维度=%s 请求条数=%s",
        len(vectors),
        emb_dim,
        top_k,
    )

    coll = get_or_create_collection()
    # Chroma n_results 不能超过 collection 内文档数；过大会报错
    try:
        total = coll.count()
    except Exception:
        total = top_k
    n_results = max(1, min(top_k, total)) if total else top_k
    logger.info(
        "[检索·向量·Chroma查询] collection内总数=%s 实际n_results=%s "
        "请求条数=%s",
        total,
        n_results,
        top_k,
    )

    # 返回结构为「batch × hits」二维；此处仅 1 条 query，取 [0]
    result = coll.query(
        query_embeddings=vectors,
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    # metadata 在入库 upsert 时写入（document_id / chunk_id / filename / heading_path）
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

    logger.info(
        "[检索·向量·结果] 命中=%s top1距离=%s ids=%s 距离=%s",
        len(items),
        items[0].distance if items else None,
        [c.chroma_id for c in items],
        [round(c.distance, 4) for c in items],
    )
    return items


def _rrf_fuse(
    vector_hits: list[RetrievedChunk],
    bm25_hits: list[bm25_store.Bm25Hit],
    *,
    final_k: int,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion：两路按排名 reciprocal 求和后截断。

    对每路第 rank 名（0-based）：贡献 1 / (RRF_K + rank + 1)。
    同分文档累加两路贡献；最终按合分降序取 final_k。
    """
    scores: dict[str, float] = {}
    payload: dict[str, RetrievedChunk] = {}

    # 向量路：保留真实 cosine distance，供后续绝对门控使用
    for rank, c in enumerate(vector_hits):
        scores[c.chroma_id] = scores.get(c.chroma_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        payload[c.chroma_id] = c

    # 纯 BM25 命中无向量 distance：用占位值，避免被绝对门控误杀关键词结果
    placeholder_distance = (
        vector_hits[0].distance if vector_hits else 0.35
    )
    bm25_only_ids: list[str] = []
    for rank, hit in enumerate(bm25_hits):
        scores[hit.chroma_id] = scores.get(hit.chroma_id, 0.0) + 1.0 / (
            _RRF_K + rank + 1
        )
        if hit.chroma_id not in payload:
            bm25_only_ids.append(hit.chroma_id)
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
    fused = [payload[cid] for cid in ordered_ids[:final_k]]
    logger.info(
        "[检索·RRF融合] rrf_k=%s 候选总数=%s 截断后=%s 占位距离=%s "
        "纯BM25条数=%s 纯BM25ids=%s 融合ids=%s rrf分=%s",
        _RRF_K,
        len(ordered_ids),
        len(fused),
        round(placeholder_distance, 4),
        len(bm25_only_ids),
        bm25_only_ids,
        [c.chroma_id for c in fused],
        [round(scores[c.chroma_id], 5) for c in fused],
    )
    return fused
