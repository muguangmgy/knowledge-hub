"""文本切分：按字符窗 max≈800 / overlap≈100；有 Markdown 标题则带 heading_path。"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 800
OVERLAP = 100


@dataclass
class TextChunk:
    """切分结果：序号、小节路径、正文。"""

    chunk_index: int
    heading_path: str
    content: str


def chunk_text(text: str) -> list[TextChunk]:
    """全文切分为 TextChunk 列表；空文本返回 []。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    sections = _split_by_headings(normalized)
    chunks: list[TextChunk] = []
    for heading, body in sections:
        heading_path = heading if heading else "正文"
        for piece in _window_split(body):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    heading_path=heading_path,
                    content=piece,
                )
            )
    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切段；无标题则整篇归入正文。"""
    pattern = re.compile(r"(?m)^(#{1,6})\s+(.+)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            sections.append(("", preface))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))
    return sections or [("", text)]


def _window_split(text: str) -> list[str]:
    """先按段落累积，超长再硬切并保留 overlap。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= MAX_CHARS:
            buf = candidate
            continue
        if buf:
            pieces.append(buf)
            overlap = buf[-OVERLAP:] if len(buf) > OVERLAP else buf
            buf = f"{overlap}\n\n{para}".strip()
            if len(buf) > MAX_CHARS:
                pieces.extend(_hard_split(buf))
                buf = ""
        else:
            pieces.extend(_hard_split(para))
            buf = ""
    if buf:
        pieces.append(buf)
    return pieces


def _hard_split(text: str) -> list[str]:
    """超长无段落边界时按字符硬切并 overlap。"""
    if len(text) <= MAX_CHARS:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - OVERLAP)
    return out
