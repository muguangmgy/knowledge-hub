from __future__ import annotations

import re
from dataclasses import dataclass

# 默认建议见设计文档 §6.4；可通过 chunk_text 参数覆盖（便于标定）
MAX_CHARS = 800
OVERLAP = 100


@dataclass
class TextChunk:
    """切分结果：序号、小节路径、正文。

    chunk_index：全文全局递增（跨 heading 不重置），与 chroma_id 后缀一致。
    heading_path：Markdown 标题栈拼成「章 > 节」；无标题则为「正文」。
    """

    chunk_index: int
    heading_path: str
    content: str


def chunk_text(
    text: str,
    *,
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP,
) -> list[TextChunk]:
    """全文切分为 TextChunk 列表；空文本返回 []。

    两层：先按 Markdown 标题分段（含层级路径），再段落窗口切分。
    相邻 chunk 会有约 overlap 字重叠（检索可能命中相近两段，属预期）。
    """
    if overlap < 0 or max_chars <= 0:
        raise ValueError("max_chars 必须 > 0，overlap 必须 >= 0")
    if overlap >= max_chars:
        raise ValueError("overlap 必须小于 max_chars，否则硬切会无法前进")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    sections = _split_by_headings(normalized)
    chunks: list[TextChunk] = []
    for heading_path, body in sections:
        path = heading_path if heading_path else "正文"
        for piece in _window_split(body, max_chars=max_chars, overlap=overlap):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    heading_path=path,
                    content=piece,
                )
            )
    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切段，heading_path 为「章 > 节」层级路径。

    无 # 标题时整篇归入 ("", text)，上层会写成「正文」。
    仅识别 Markdown；docx 需在 parser 侧把 Heading 样式转成 # 行后才能受益。
    """
    pattern = re.compile(r"(?m)^(#{1,6})\s+(.+)$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            sections.append(("", preface))

    # 标题栈：[(level, title), ...]，用于拼 heading_path
    stack: list[tuple[int, str]] = []

    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        heading_path = " > ".join(t for _, t in stack)

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading_path, body))

    return sections or [("", text)]


def _window_split(
    text: str, *, max_chars: int, overlap: int
) -> list[str]:
    """先按段落累积，超长再硬切并保留 overlap。

    吐出一段后，会把该段尾部 overlap 字拼进下一段开头（内容重复是预期行为）。
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []

    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        candidate = f"{buf}\n\n{para}".strip() if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        if buf:
            pieces.append(buf)
            # 与下一段重叠：取已输出缓冲的尾部
            tail = buf[-overlap:] if len(buf) > overlap else buf
            buf = f"{tail}\n\n{para}".strip()
            if len(buf) > max_chars:
                pieces.extend(
                    _hard_split(buf, max_chars=max_chars, overlap=overlap)
                )
                buf = ""
        else:
            pieces.extend(_hard_split(para, max_chars=max_chars, overlap=overlap))
            buf = ""
    if buf:
        pieces.append(buf)
    return pieces


def _hard_split(text: str, *, max_chars: int, overlap: int) -> list[str]:
    """超长无段落边界时按字符硬切并 overlap；尽量在句号等标点处落刀。"""
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            window = text[start:end]
            # 后半段找最近句界，避免经常切在半句中间
            cut = -1
            for mark in ("。", "！", "？", "；", "\n", ".", "!", "?"):
                pos = window.rfind(mark)
                if pos > cut:
                    cut = pos
            if cut >= max_chars // 2:
                end = start + cut + 1
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return out
