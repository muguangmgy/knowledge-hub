from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.document import Document

logger = logging.getLogger(__name__)


@dataclass
class Bm25Hit:
    chroma_id: str
    document_id: int
    chunk_id: int
    filename: str
    heading_path: str
    content: str
    score: float


@dataclass
class _DocEntry:
    chroma_id: str
    document_id: int
    chunk_id: int
    filename: str
    title: str
    heading_path: str
    content: str
    tokens: list[str]


_lock = threading.RLock()
_entries: list[_DocEntry] = []
_by_id: dict[str, _DocEntry] = {}
_bm25: BM25Okapi | None = None


def _tokenize(text: str) -> list[str]:
    """中文检索分词；过滤空白；英文统一小写（避免 CRM/crm 对不上）。"""
    return [
        t.strip().lower()
        for t in jieba.lcut_for_search(text or "")
        if t and t.strip()
    ]


def _index_text(title: str, filename: str, heading_path: str, content: str) -> str:
    """标题/文件名优先进索引，便于短词命中。"""
    return f"{title or ''} {filename or ''} {heading_path or ''} {content or ''}"


def _rebuild_locked() -> None:
    global _bm25
    if not _entries:
        _bm25 = None
        return
    corpus = [e.tokens for e in _entries]
    _bm25 = BM25Okapi(corpus)


def rebuild_from_db(db: Session) -> int:
    """从 MySQL 全量重建索引（启动时调用）。"""
    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .order_by(Chunk.id.asc())
    ).all()

    entries: list[_DocEntry] = []
    by_id: dict[str, _DocEntry] = {}
    for chunk, doc in rows:
        text = _index_text(doc.title, doc.filename, chunk.heading_path, chunk.content)
        entry = _DocEntry(
            chroma_id=chunk.chroma_id,
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            filename=doc.filename,
            title=doc.title,
            heading_path=chunk.heading_path or "",
            content=chunk.content or "",
            tokens=_tokenize(text),
        )
        entries.append(entry)
        by_id[entry.chroma_id] = entry

    with _lock:
        global _entries, _by_id
        _entries = entries
        _by_id = by_id
        _rebuild_locked()

    logger.info("[BM25·重建] 切片数=%s", len(entries))
    return len(entries)


def upsert_chunks(
    items: list[dict],
) -> None:
    """入库后增量写入；同 chroma_id 覆盖。items 字段见 ingest 调用处。"""
    if not items:
        return
    with _lock:
        for item in items:
            cid = str(item["chroma_id"])
            text = _index_text(
                str(item.get("title") or ""),
                str(item.get("filename") or ""),
                str(item.get("heading_path") or ""),
                str(item.get("content") or ""),
            )
            entry = _DocEntry(
                chroma_id=cid,
                document_id=int(item["document_id"]),
                chunk_id=int(item["chunk_id"]),
                filename=str(item.get("filename") or ""),
                title=str(item.get("title") or ""),
                heading_path=str(item.get("heading_path") or ""),
                content=str(item.get("content") or ""),
                tokens=_tokenize(text),
            )
            if cid in _by_id:
                for i, e in enumerate(_entries):
                    if e.chroma_id == cid:
                        _entries[i] = entry
                        break
                _by_id[cid] = entry
            else:
                _entries.append(entry)
                _by_id[cid] = entry
        _rebuild_locked()
    logger.info("[BM25·写入] 新增=%s 当前总数=%s", len(items), len(_entries))


def remove_ids(chroma_ids: list[str]) -> None:
    """删除文档后移除对应切片。"""
    if not chroma_ids:
        return
    id_set = set(chroma_ids)
    with _lock:
        global _entries, _by_id
        _entries = [e for e in _entries if e.chroma_id not in id_set]
        for cid in id_set:
            _by_id.pop(cid, None)
        _rebuild_locked()
    logger.info("[BM25·删除] 移除=%s 当前总数=%s", len(id_set), len(_entries))


def search(query: str, *, top_k: int) -> list[Bm25Hit]:
    """BM25 关键词检索；无索引或空 query → []。"""
    query = (query or "").strip()
    if not query or top_k <= 0:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    with _lock:
        if _bm25 is None or not _entries:
            return []
        scores = _bm25.get_scores(tokens)
        # 取分最高的 top_k（分数为 0 的也截断掉）
        ranked = sorted(
            ((float(scores[i]), _entries[i]) for i in range(len(_entries))),
            key=lambda x: x[0],
            reverse=True,
        )

    hits: list[Bm25Hit] = []
    for score, entry in ranked:
        if score <= 0:
            break
        hits.append(
            Bm25Hit(
                chroma_id=entry.chroma_id,
                document_id=entry.document_id,
                chunk_id=entry.chunk_id,
                filename=entry.filename,
                heading_path=entry.heading_path,
                content=entry.content,
                score=score,
            )
        )
        if len(hits) >= top_k:
            break

    logger.info(
        "[检索·BM25·结果] 问题=%r 分词=%s 命中=%s 请求条数=%s "
        "ids=%s 分数=%s",
        query,
        tokens,
        len(hits),
        top_k,
        [h.chroma_id for h in hits],
        [round(h.score, 4) for h in hits],
    )
    return hits
