from pathlib import Path

import pymupdf
from docx import Document as DocxDocument

from app.common.errors import AppError, ErrorCode

ALLOWED_TYPES = frozenset({"pdf", "docx", "md", "txt"})


def detect_file_type(filename: str) -> str:
    """白名单校验；不支持类型（含 .doc）→ 42201。"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_TYPES:
        raise AppError(
            ErrorCode.UNSUPPORTED_TYPE,
            f"不支持的文件类型: .{suffix or '?'}",
            http_status=422,
        )
    return suffix


def parse_bytes(file_type: str, data: bytes) -> str:
    """按类型提取纯文本；无有效正文由上层回滚为 50001。"""
    if file_type == "pdf":
        return _parse_pdf(data)
    if file_type == "docx":
        return _parse_docx(data)
    if file_type in {"md", "txt"}:
        return data.decode("utf-8", errors="ignore")
    raise AppError(ErrorCode.UNSUPPORTED_TYPE, "不支持的文件类型", http_status=422)


def _parse_pdf(data: bytes) -> str:
    """PDF → 纯文本（按页拼接）。"""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text") or "")
        return "\n".join(parts)
    finally:
        doc.close()


def _parse_docx(data: bytes) -> str:
    """docx → 非空段落文本拼接。"""
    from io import BytesIO

    document = DocxDocument(BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs if p.text)
