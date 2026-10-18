from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode
from app.common.logging_util import event_msg
from app.ingest.chunker import chunk_text, text_for_embedding
from app.ingest.parser import ALLOWED_TYPES, detect_file_type, parse_bytes
from app.models.chunk import Chunk
from app.models.document import Document
from app.rag import bm25_store, chroma_store
from app.rag.embedding import embed_texts

logger = logging.getLogger(__name__)

# 批量导入只接受 2～6 个；单文件仍走 ingest_upload
BATCH_UPLOAD_MIN = 2
BATCH_UPLOAD_MAX = 6
_COLLATION_SAFE = re.compile(r"^[A-Za-z0-9_]+$")
_filename_collation_cache: str | None = None


def list_documents(db: Session) -> list[dict]:
    """共享库全量列表（需登录）。"""
    rows = db.scalars(select(Document).order_by(Document.id.desc())).all()
    return [_doc_to_dict(d) for d in rows]


def get_document(db: Session, document_id: int) -> dict:
    """文档详情；不存在 → 40401。"""
    doc = db.get(Document, document_id)
    if doc is None:
        raise AppError(ErrorCode.NOT_FOUND, "文档不存在", http_status=404)
    return _doc_to_dict(doc)


def ingest_upload(db: Session, *, filename: str, data: bytes) -> dict:
    """同步入库：解析切分 Embedding → 写库落盘 → Chroma；失败回滚。"""
    settings = get_settings()
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise AppError(ErrorCode.UNSUPPORTED_TYPE, "非法文件名", http_status=422)

    file_type = detect_file_type(safe_name)
    max_bytes = settings.INGEST_MAX_MB * 1024 * 1024
    size_bytes = len(data)
    if size_bytes > max_bytes:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, "超过上传大小上限", http_status=413)
    if size_bytes == 0:
        raise AppError(ErrorCode.INGEST_FAILED, "未能提取有效文本", http_status=500)

    # 预检同名；并发下仍可能撞 UNIQUE，由 IntegrityError 转 40901
    exists = db.scalar(select(Document).where(Document.filename == safe_name))
    if exists is not None:
        raise AppError(ErrorCode.DOC_EXISTS, "同名文档已存在", http_status=409)

    text = parse_bytes(file_type, data).strip()
    if not text:
        raise AppError(ErrorCode.INGEST_FAILED, "未能提取有效文本", http_status=500)

    pieces = chunk_text(text)
    if not pieces:
        raise AppError(ErrorCode.INGEST_FAILED, "未能提取有效文本", http_status=500)

    # 耗时长的 Embedding 放在落库之前，失败时通常无库行
    # 向量输入带 heading_path；Chroma document 仍写纯 content（见下方 upsert）
    embeddings = embed_texts(
        [text_for_embedding(p.heading_path, p.content) for p in pieces]
    )

    title = Path(safe_name).stem
    document: Document | None = None
    chroma_ids: list[str] = []
    file_path: Path | None = None

    try:
        document = Document(
            title=title,
            filename=safe_name,
            file_path="",  # flush 拿到 id 后再填
            file_type=file_type,
            size_bytes=size_bytes,
        )
        db.add(document)
        db.flush()

        rel_path = f"{document.id}/{safe_name}"
        document.file_path = rel_path
        abs_dir = settings.kb_dir / str(document.id)
        abs_dir.mkdir(parents=True, exist_ok=True)
        file_path = abs_dir / safe_name
        file_path.write_bytes(data)

        chunk_rows: list[Chunk] = []
        metadatas: list[dict] = []
        for piece, emb in zip(pieces, embeddings, strict=True):
            chroma_id = f"{document.id}_{piece.chunk_index}"
            chroma_ids.append(chroma_id)
            row = Chunk(
                document_id=document.id,
                chunk_index=piece.chunk_index,
                heading_path=piece.heading_path,
                content=piece.content,
                chroma_id=chroma_id,
            )
            chunk_rows.append(row)
            metadatas.append(
                {
                    "document_id": document.id,
                    "chunk_id": 0,
                    "heading_path": piece.heading_path[:500],
                    "filename": safe_name,
                }
            )
            db.add(row)

        db.flush()
        for i, row in enumerate(chunk_rows):
            metadatas[i]["chunk_id"] = row.id

        # Chroma 最后写：此前失败只需回滚库行与文件
        chroma_store.upsert_chunks(
            ids=chroma_ids,
            documents=[p.content for p in pieces],
            embeddings=embeddings,
            metadatas=metadatas,
        )
        # BM25 与 Chroma 同步；内存索引，失败不回滚已成功入库
        bm25_store.upsert_chunks(
            [
                {
                    "chroma_id": row.chroma_id,
                    "document_id": row.document_id,
                    "chunk_id": row.id,
                    "filename": safe_name,
                    "title": title,
                    "heading_path": row.heading_path,
                    "content": row.content,
                }
                for row in chunk_rows
            ]
        )
        db.commit()
        db.refresh(document)
        logger.info(
            event_msg(
                "ingest_upload",
                document_id=document.id,
                filename=safe_name,
                chunks=len(chunk_rows),
                size_bytes=size_bytes,
            )
        )
        return _doc_to_dict(document)
    except IntegrityError:
        db.rollback()
        _cleanup_partial(settings, document, file_path, chroma_ids)
        raise AppError(ErrorCode.DOC_EXISTS, "同名文档已存在", http_status=409)
    except AppError:
        db.rollback()
        _cleanup_partial(settings, document, file_path, chroma_ids)
        raise
    except Exception as exc:
        db.rollback()
        _cleanup_partial(settings, document, file_path, chroma_ids)
        logger.warning(
            event_msg("ingest_upload", filename=safe_name, err=exc)
        )
        raise AppError(
            ErrorCode.INGEST_FAILED, f"入库失败: {exc}", http_status=500
        ) from exc


def delete_document(db: Session, document_id: int) -> None:
    """先清 Chroma；失败整单失败（50000），不动库与文件。"""
    settings = get_settings()
    doc = db.get(Document, document_id)
    if doc is None:
        raise AppError(ErrorCode.NOT_FOUND, "文档不存在", http_status=404)

    filename = doc.filename
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document_id)
    ).all()
    chroma_ids = [c.chroma_id for c in chunks]

    try:
        chroma_store.delete_ids(chroma_ids)
    except Exception as exc:
        raise AppError(
            ErrorCode.INTERNAL, f"Chroma 删除失败: {exc}", http_status=500
        ) from exc

    bm25_store.remove_ids(chroma_ids)

    for c in chunks:
        db.delete(c)

    file_path = settings.kb_dir / doc.file_path
    doc_dir = settings.kb_dir / str(document_id)
    db.delete(doc)
    db.commit()

    if file_path.exists():
        file_path.unlink()
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)

    logger.info(
        event_msg(
            "delete_document",
            document_id=document_id,
            filename=filename,
            chunks=len(chroma_ids),
        )
    )


def reingest_document(db: Session, document_id: int) -> dict:
    """用磁盘原文件按当前解析/切分规则原地重建索引。

    保留 document 行与原文件；先算完 Embedding，再替换 chunk / Chroma / BM25。
    """
    settings = get_settings()
    doc = db.get(Document, document_id)
    if doc is None:
        raise AppError(ErrorCode.NOT_FOUND, "文档不存在", http_status=404)

    abs_path = settings.kb_dir / doc.file_path
    if not abs_path.is_file():
        raise AppError(
            ErrorCode.INGEST_FAILED,
            "原文件不存在，无法重新解析",
            http_status=500,
        )

    data = abs_path.read_bytes()
    if not data:
        raise AppError(ErrorCode.INGEST_FAILED, "原文件为空，无法重新解析", http_status=500)

    file_type = detect_file_type(doc.filename)
    text = parse_bytes(file_type, data).strip()
    if not text:
        raise AppError(ErrorCode.INGEST_FAILED, "未能提取有效文本", http_status=500)

    pieces = chunk_text(text)
    if not pieces:
        raise AppError(ErrorCode.INGEST_FAILED, "未能提取有效文本", http_status=500)

    embeddings = embed_texts(
        [text_for_embedding(p.heading_path, p.content) for p in pieces]
    )

    old_chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document_id)
    ).all()
    old_chroma_ids = [c.chroma_id for c in old_chunks]

    try:
        chroma_store.delete_ids(old_chroma_ids)
    except Exception as exc:
        raise AppError(
            ErrorCode.INTERNAL, f"Chroma 删除失败: {exc}", http_status=500
        ) from exc

    bm25_store.remove_ids(old_chroma_ids)

    for c in old_chunks:
        db.delete(c)
    db.flush()

    chroma_ids: list[str] = []
    chunk_rows: list[Chunk] = []
    metadatas: list[dict] = []
    try:
        for piece in pieces:
            chroma_id = f"{doc.id}_{piece.chunk_index}"
            chroma_ids.append(chroma_id)
            row = Chunk(
                document_id=doc.id,
                chunk_index=piece.chunk_index,
                heading_path=piece.heading_path,
                content=piece.content,
                chroma_id=chroma_id,
            )
            chunk_rows.append(row)
            metadatas.append(
                {
                    "document_id": doc.id,
                    "chunk_id": 0,
                    "heading_path": piece.heading_path[:500],
                    "filename": doc.filename,
                }
            )
            db.add(row)

        db.flush()
        for i, row in enumerate(chunk_rows):
            metadatas[i]["chunk_id"] = row.id

        chroma_store.upsert_chunks(
            ids=chroma_ids,
            documents=[p.content for p in pieces],
            embeddings=embeddings,
            metadatas=metadatas,
        )
        bm25_store.upsert_chunks(
            [
                {
                    "chroma_id": row.chroma_id,
                    "document_id": row.document_id,
                    "chunk_id": row.id,
                    "filename": doc.filename,
                    "title": doc.title,
                    "heading_path": row.heading_path,
                    "content": row.content,
                }
                for row in chunk_rows
            ]
        )
        db.commit()
        db.refresh(doc)
    except AppError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.warning(
            event_msg(
                "reingest_document",
                document_id=document_id,
                filename=doc.filename,
                err=exc,
            )
        )
        raise AppError(
            ErrorCode.INGEST_FAILED, f"重新解析失败: {exc}", http_status=500
        ) from exc

    logger.info(
        event_msg(
            "reingest_document",
            document_id=doc.id,
            filename=doc.filename,
            chunks=len(chunk_rows),
        )
    )
    return _doc_to_dict(doc)


def reingest_all_documents(db: Session) -> dict:
    """按当前列表顺序逐个重新解析；单项失败记入 errors，不中断其余。"""
    rows = db.scalars(select(Document).order_by(Document.id.asc())).all()
    ids = [d.id for d in rows]
    ok_items: list[dict] = []
    errors: list[dict] = []
    for doc_id in ids:
        try:
            ok_items.append(reingest_document(db, doc_id))
        except AppError as exc:
            errors.append({"documentId": doc_id, "message": exc.message})
        except Exception as exc:
            errors.append({"documentId": doc_id, "message": str(exc)})
    logger.info(
        event_msg(
            "reingest_all_documents",
            total=len(ids),
            ok=len(ok_items),
            failed=len(errors),
        )
    )
    return {
        "total": len(ids),
        "ok": len(ok_items),
        "failed": len(errors),
        "items": ok_items,
        "errors": errors,
    }


def ingest_uploads(db: Session, files: list[tuple[str, bytes]]) -> dict:
    """批量入库：预检后逐份 ingest_upload；部分成功不回滚。"""
    total = len(files)
    if total < BATCH_UPLOAD_MIN or total > BATCH_UPLOAD_MAX:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"批量导入须提交 {BATCH_UPLOAD_MIN}～{BATCH_UPLOAD_MAX} 个文件",
            http_status=400,
        )

    collation = _document_filename_collation(db)
    ok_items: list[dict] = []
    errors: list[dict] = []
    passed_names: list[str] = []
    pending: list[tuple[int, str, bytes]] = []

    # 先整批预检：失败记 precheck，不调用 ingest_upload；index 对应该次提交顺序
    for index, (filename, data) in enumerate(files):
        pre = _precheck_batch_file(
            db,
            filename=filename,
            data=data,
            passed_names=passed_names,
            collation=collation,
        )
        if pre is not None:
            errors.append(
                {
                    "index": index,
                    "filename": pre["filename"],
                    "phase": "precheck",
                    "reason": pre["reason"],
                    "message": pre["message"],
                }
            )
            continue
        safe_name = Path(filename).name
        passed_names.append(safe_name)
        pending.append((index, safe_name, data))

    # 通过预检的按原顺序完整入库；单份失败不回滚已成功项
    for index, safe_name, data in pending:
        try:
            doc = ingest_upload(db, filename=safe_name, data=data)
            item = dict(doc)
            item["index"] = index
            ok_items.append(item)
        except AppError as exc:
            errors.append(
                {
                    "index": index,
                    "filename": safe_name,
                    "phase": "process",
                    "reason": _map_ingest_process_reason(exc),
                    "message": exc.message,
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "index": index,
                    "filename": safe_name,
                    "phase": "process",
                    "reason": "other",
                    "message": str(exc),
                }
            )

    logger.info(
        event_msg(
            "ingest_uploads",
            total=total,
            ok=len(ok_items),
            failed=len(errors),
        )
    )
    return {
        "total": total,
        "ok": len(ok_items),
        "failed": len(errors),
        "items": ok_items,
        "errors": errors,
    }


def delete_documents(db: Session, ids: list[int]) -> dict:
    """批量物理删除：逐条 delete_document；部分成功不回滚。"""
    if not ids:
        raise AppError(ErrorCode.BAD_REQUEST, "ids 不能为空", http_status=400)
    for item in ids:
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise AppError(ErrorCode.BAD_REQUEST, "ids 须为正整数", http_status=400)

    # 按首次出现去重，重复 id 只删一次
    unique: list[int] = []
    seen: set[int] = set()
    for doc_id in ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        unique.append(doc_id)

    ok_items: list[dict] = []
    errors: list[dict] = []
    for doc_id in unique:
        # 删除前记下文件名，不存在或删除失败时失败项仍能带上
        doc = db.get(Document, doc_id)
        filename = doc.filename if doc is not None else ""
        try:
            delete_document(db, doc_id)
            ok_items.append({"documentId": doc_id, "filename": filename})
        except AppError as exc:
            reason = (
                "not_found"
                if exc.code == ErrorCode.NOT_FOUND
                else "delete_failed"
            )
            errors.append(
                {
                    "documentId": doc_id,
                    "filename": filename,
                    "reason": reason,
                    "message": exc.message,
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "documentId": doc_id,
                    "filename": filename,
                    "reason": "delete_failed",
                    "message": str(exc),
                }
            )

    logger.info(
        event_msg(
            "delete_documents",
            total=len(unique),
            ok=len(ok_items),
            failed=len(errors),
        )
    )
    return {
        "total": len(unique),
        "ok": len(ok_items),
        "failed": len(errors),
        "items": ok_items,
        "errors": errors,
    }


def _document_filename_collation(db: Session) -> str:
    """读取 document.filename 列 collation；结果缓存。"""
    global _filename_collation_cache
    if _filename_collation_cache is not None:
        return _filename_collation_cache
    row = db.execute(
        text(
            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'document' AND COLUMN_NAME = 'filename'"
        )
    ).first()
    collation = (row[0] if row else None) or "utf8mb4_general_ci"
    if not _COLLATION_SAFE.match(collation):
        raise AppError(
            ErrorCode.INTERNAL,
            f"非法 filename collation: {collation}",
            http_status=500,
        )
    _filename_collation_cache = collation
    return collation


def _filenames_equal_under_collation(
    db: Session, left: str, right: str, collation: str
) -> bool:
    """用列 collation 比较两个文件名是否相等（批内互比）。"""
    result = db.execute(
        text(f"SELECT :left COLLATE {collation} = :right COLLATE {collation}"),
        {"left": left, "right": right},
    ).scalar()
    return bool(result)


def _precheck_batch_file(
    db: Session,
    *,
    filename: str,
    data: bytes,
    passed_names: list[str],
    collation: str,
) -> dict | None:
    """单份预检；通过返回 None，否则返回 filename/reason/message。"""
    safe_name = Path(filename).name
    display = safe_name or (filename or "")

    if not safe_name or safe_name in {".", ".."}:
        return {
            "filename": display,
            "reason": "other",
            "message": "非法文件名",
        }

    suffix = Path(safe_name).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_TYPES:
        return {
            "filename": safe_name,
            "reason": "other",
            "message": f"不支持的文件类型: .{suffix or '?'}",
        }

    size_bytes = len(data)
    if size_bytes == 0:
        return {
            "filename": safe_name,
            "reason": "other",
            "message": "文件为空",
        }

    max_bytes = get_settings().INGEST_MAX_MB * 1024 * 1024
    if size_bytes > max_bytes:
        return {
            "filename": safe_name,
            "reason": "too_large",
            "message": "超过上传大小上限",
        }

    exists = db.scalar(select(Document).where(Document.filename == safe_name))
    if exists is not None:
        return {
            "filename": safe_name,
            "reason": "duplicate",
            "message": "同名文档已存在",
        }

    for prior in passed_names:
        if _filenames_equal_under_collation(db, safe_name, prior, collation):
            return {
                "filename": safe_name,
                "reason": "duplicate",
                "message": "同名文档已存在",
            }

    return None


def _map_ingest_process_reason(exc: AppError) -> str:
    """将 ingest_upload 抛出的 AppError 映射为批内 reason。"""
    if exc.code == ErrorCode.DOC_EXISTS:
        return "duplicate"
    if exc.code == ErrorCode.PAYLOAD_TOO_LARGE:
        return "too_large"
    if exc.code == ErrorCode.INGEST_FAILED:
        # 空文本算解析失败；Embedding/Chroma/落盘被包成「入库失败:」算其他
        if exc.message == "未能提取有效文本":
            return "parse_failed"
        if exc.message.startswith("入库失败:"):
            return "other"
        return "other"
    return "other"


def _cleanup_partial(
    settings,
    document: Document | None,
    file_path: Path | None,
    chroma_ids: list[str],
) -> None:
    """入库失败后尽力清理已写向量与磁盘文件（库事务已 rollback）。"""
    if chroma_ids:
        try:
            chroma_store.delete_ids(chroma_ids)
        except Exception:
            pass
    if file_path is not None and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass
    if document is not None and document.id:
        doc_dir = settings.kb_dir / str(document.id)
        if doc_dir.exists():
            shutil.rmtree(doc_dir, ignore_errors=True)


def _doc_to_dict(doc: Document) -> dict:
    """文档 ORM → API camelCase。"""
    return {
        "id": doc.id,
        "title": doc.title,
        "filename": doc.filename,
        "filePath": doc.file_path,
        "fileType": doc.file_type,
        "sizeBytes": doc.size_bytes,
        "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        "updatedAt": doc.updated_at.isoformat() if doc.updated_at else None,
    }
