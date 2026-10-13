from __future__ import annotations

import time

from langchain_openai import OpenAIEmbeddings

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode

_BATCH_SIZE = 16
_MAX_RETRIES = 3


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化；失败重试后仍失败 → INGEST_FAILED(50001)。"""
    if not texts:
        return []

    settings = get_settings()
    if not settings.EMBEDDING_API_KEY:
        raise AppError(
            ErrorCode.INGEST_FAILED, "未配置 EMBEDDING_API_KEY", http_status=500
        )

    client = OpenAIEmbeddings(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL.rstrip("/"),
        model=settings.EMBEDDING_MODEL,
        timeout=120.0,
        max_retries=0,  # 重试由本模块控制
        chunk_size=_BATCH_SIZE,
    )

    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        vectors.extend(_embed_batch(client, batch))
    return vectors


def _embed_batch(client: OpenAIEmbeddings, batch: list[str]) -> list[list[float]]:
    """单批向量化，失败有限次重试。"""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            vectors = client.embed_documents(batch)
            if len(vectors) != len(batch):
                raise AppError(
                    ErrorCode.INGEST_FAILED,
                    "Embedding 返回条数与输入不一致",
                    http_status=500,
                )
            return vectors
        except AppError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt + 1 < _MAX_RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
            break

    raise AppError(
        ErrorCode.INGEST_FAILED,
        f"Embedding 失败: {last_error}",
        http_status=500,
    ) from last_error
