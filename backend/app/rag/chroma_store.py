from __future__ import annotations

from typing import Any

from chromadb.api.models.Collection import Collection

from app.common.chroma import get_chroma

COLLECTION_NAME = "kh_chunks"


def get_or_create_collection() -> Collection:
    """必须指定 hnsw:space=cosine（禁止依赖默认 L2）。"""
    client = get_chroma()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    *,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]],
) -> None:
    """批量 upsert 向量切片。"""
    if not ids:
        return
    coll = get_or_create_collection()
    coll.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def delete_ids(ids: list[str]) -> None:
    """删除失败由调用方转为整单失败（删除文档时）。"""
    if not ids:
        return
    coll = get_or_create_collection()
    coll.delete(ids=ids)
