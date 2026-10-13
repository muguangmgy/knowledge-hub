from io import BytesIO
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
    """按类型提取纯文本；无有效正文由上层回滚为 50001。

    docx 的 Heading 样式会转成 Markdown # 行，便于 chunker 填 heading_path。
    pdf 仍为纯文本（无可靠大纲），切分侧多为「正文」。
    """
    try:
        if file_type == "pdf":
            return _parse_pdf(data)
        if file_type == "docx":
            return _parse_docx(data)
        if file_type in {"md", "txt"}:
            return _decode_text(data)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.INGEST_FAILED,
            f"文档解析失败: {exc}",
            http_status=500,
        ) from exc
    raise AppError(ErrorCode.UNSUPPORTED_TYPE, "不支持的文件类型", http_status=422)


def _decode_text(data: bytes) -> str:
    """优先 UTF-8；失败再试 GBK，避免中文 Windows 文本静默丢字。"""
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 仍失败则替换非法字节，保证入库链路可继续、由上层判空
    return data.decode("utf-8", errors="replace")


def _parse_pdf(data: bytes) -> str:
    """PDF → 纯文本（按页拼接）。扫描件/纯图无字时上层会判无正文。"""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text") or "")
        return "\n".join(parts)
    finally:
        doc.close()


def _parse_docx(data: bytes) -> str:
    """docx → 文本；Heading 样式转为 # 标题行；表格单元格一并抽出。"""
    document = DocxDocument(BytesIO(data))
    lines: list[str] = []

    for p in document.paragraphs:
        text = (p.text or "").strip()
        if not text:
            continue
        level = _docx_heading_level(p)
        if level:
            lines.append(f"{'#' * level} {text}")
        else:
            lines.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            cells = [c for c in cells if c]
            if cells:
                lines.append("\t".join(cells))

    return "\n\n".join(lines)


def _docx_heading_level(paragraph) -> int | None:
    """从样式名解析 Heading 1..9；非标题返回 None。"""
    style = paragraph.style
    if style is None or not style.name:
        return None
    name = style.name.strip()
    # 常见：Heading 1 / 标题 1
    for prefix in ("Heading ", "标题 "):
        if name.startswith(prefix):
            rest = name[len(prefix) :].strip()
            if rest.isdigit():
                level = int(rest)
                if 1 <= level <= 6:
                    return level
    if name in {"Title", "标题"}:
        return 1
    return None
