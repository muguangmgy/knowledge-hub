from __future__ import annotations

import io
import re

# 聊天文末可能误带的发送说明，生成 PDF 时一律剥掉
_DELIVERY_NOTE_RE = re.compile(
    r"(?:\n|^)*(?:报告)?已发送至[^\n]*"
    r"|(?:\n|^)*未发送邮件[^\n]*"
    r"|(?:\n|^)*邮件发送失败[^\n]*"
    r"|(?:\n|^)*当前仅支持发送至系统配置邮箱[^\n]*",
)

_HTML_STYLE = """
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", "SimSun", sans-serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #1a2332;
}
h1 { font-size: 18pt; margin: 0 0 12pt; }
h2 { font-size: 14pt; margin: 16pt 0 8pt; border-bottom: 1px solid #e2e6eb; padding-bottom: 4pt; }
h3 { font-size: 12pt; margin: 12pt 0 6pt; }
p, li { margin: 4pt 0; }
table { width: 100%; border-collapse: collapse; margin: 10pt 0; font-size: 9.5pt; }
th, td { border: 1px solid #c9d0d8; padding: 5pt 6pt; text-align: left; vertical-align: top; }
th { background: #f7f8fa; font-weight: 600; }
hr { border: none; border-top: 1px solid #e2e6eb; margin: 14pt 0; }
"""


def strip_delivery_notes(markdown: str) -> str:
    """去掉「已发送至…」等投递说明，避免进 PDF。"""
    text = (markdown or "").rstrip()
    text = _DELIVERY_NOTE_RE.sub("", text)
    return text.strip()


def markdown_to_pdf_bytes(markdown: str) -> bytes:
    """Markdown → HTML → PDF（PyMuPDF Story，无额外系统依赖）。

    启用 nl2br，与前端 marked ``breaks: true`` 对齐单换行版式；
    生成前剥掉投递说明（不进 PDF）。
    """
    import markdown as md
    import pymupdf

    clean = strip_delivery_notes(markdown)
    # nl2br：与前端 marked breaks:true 对齐，单换行保留为 <br>
    # （否则「报告日期/股票代码…」在 PDF 会被挤成一行）
    body = md.markdown(
        clean,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_HTML_STYLE}</style></head><body>{body}</body></html>"
    )

    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (36, 36, -36, -36)
    story = pymupdf.Story(html=html)
    bio = io.BytesIO()
    writer = pymupdf.DocumentWriter(bio)
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    data = bio.getvalue()
    if not data:
        raise RuntimeError("pdf empty")
    return data


def safe_pdf_filename(stem: str) -> str:
    """把标题收成合法 PDF 文件名（替换非法字符、截断长度）。"""
    raw = (stem or "report").strip() or "report"
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", raw)
    return f"{safe[:80]}.pdf"
