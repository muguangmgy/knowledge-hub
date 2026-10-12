from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.common.db import get_db
from app.common.response import ok
from app.models.user import User
from app.services import ingest as ingest_service

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """共享库文档列表。"""
    return ok(ingest_service.list_documents(db))


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """文档详情。"""
    return ok(ingest_service.get_document(db, document_id))


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """同步入库上传（长耗时）。"""
    data = await file.read()
    filename = file.filename or "unnamed.txt"
    doc = ingest_service.ingest_upload(db, filename=filename, data=data)
    return ok(doc)


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """物理删除：Chroma → MySQL → 文件。"""
    ingest_service.delete_document(db, document_id)
    return ok({})
