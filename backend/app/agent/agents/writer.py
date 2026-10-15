from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date

from app.agent.logging_util import check_deadline
from app.agent.tools.finance import format_finance_section_md
from app.llm.client import chat_completion, chat_completion_stream

TIMEOUT_MSG = "分析超时，请稍后重试。"
NO_SYMBOL_MSG = "请说明股票名称或代码"
# 免责声明不交给模型写，避免漏写或改口径
DISCLAIMER = (
    "\n\n---\n\n"
    "**免责声明**：本报告由系统根据公开数据自动生成，仅供参考，"
    "**不构成任何投资建议**。市场有风险，决策需谨慎。"
)

_SYSTEM_TEMPLATE = """你是股票投研报告撰写助手。根据给定 JSON 数据写 Markdown 研报。

【输出格式】严格按以下结构，标题原样使用，不要自创章节：

# {asset_name}（{asset_code}）深度分析报告

报告日期：{report_date}
股票代码：{asset_code}
股票名称：{asset_name}
{meta_extra}
---
{section_one}
## 二、股价走势分析

按时间阶段划分走势（如「9月中旬」「9月末至10月上旬」「10月中旬」），每阶段 1~3 句话。
依据 JSON 中 `market_data.bars`（腾讯日 K：开/收/高/低）撰写，不要罗列每日数字。

{section_news}
{section_finance}
## 五、简要结论

2~4 句话概括走势、财务与关注点。

【硬性约束】
- 全文不超过 600 字（不含系统已给出的核心数据表、资讯列表与财务表）。
- 禁止编造任何数字；若已给出「一、核心数据概览」表格，须原样保留，不得增删行或改数，也勿再写「请原样保留」之类说明。
- 若已给出「三、资讯要点」全文（含 Markdown 链接），须原样保留，不得改写标题、删改链接或增删条目。
- 若已给出「四、财务要点」表格，须原样保留，不得改数或增删行列。
- 只输出报告正文，不要套代码块。
- 不要输出免责声明（由系统追加）。
"""

NEWS_MAX = 6


def _news_date_only(raw: str) -> str:
    """资讯时间取日期部分（YYYY-MM-DD），去掉时分秒。"""
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else text.split()[0]


def format_news_section_md(news: list | None) -> str:
    """将腾讯资讯格式化为「三、资讯要点」Markdown（含可点击链接，最多 6 条）。

    条目格式：``日期 券商：标题``（标题可带链接）。
    """
    lines: list[str] = []
    if isinstance(news, list):
        for it in news[:NEWS_MAX]:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip() or "无标题"
            date_s = _news_date_only(str(it.get("time") or ""))
            url = str(it.get("url") or "").strip()
            source = str(it.get("source") or "").strip()
            if url.startswith("//"):
                url = "https:" + url
            title_md = f"[{title}]({url})" if url else title
            parts: list[str] = []
            if date_s:
                parts.append(date_s)
            if source:
                parts.append(f"{source}：{title_md}")
            else:
                parts.append(title_md)
            lines.append("- " + " ".join(parts))
    body = "\n".join(lines) if lines else "暂无直接相关资讯。"
    return f"## 三、资讯要点\n\n{body}\n\n"


def writer_node(state: dict) -> dict:
    """综合 Analyst 数据写 Markdown；超时/无标的走硬编码；免责声明由系统追加。"""
    hardcoded, messages, table_md, news_section_md, finance_section_md = prepare_writer(
        state
    )
    if hardcoded is not None:
        body = hardcoded
    else:
        assert messages is not None
        report = chat_completion(messages)
        body = finalize_writer_body(
            (report or "").strip(),
            table_md,
            news_section_md,
            finance_section_md,
        )
    return {"report_md": append_disclaimer(body)}


def prepare_writer(
    state: dict,
) -> tuple[str | None, list[dict[str, str]] | None, str, str, str]:
    """解析 Writer 输入，供同步 writer_node 与流式 iter_writer_deltas 共用。

    返回 ``(硬编码正文不含免责声明, LLM messages, table_md, news_section_md, finance_section_md)``。
    超时/无标的 → 硬编码非空、messages 为 None；
    有标的 LLM 路径 → 硬编码为 None、messages 非空。
    """
    patch = check_deadline(state)
    timed_out = bool(state.get("timed_out") or patch.get("timed_out"))
    if timed_out:
        return TIMEOUT_MSG, None, "", "", ""

    if state.get("skip_analysts"):
        return NO_SYMBOL_MSG, None, "", "", ""

    intent = state.get("intent") or {}
    quote = state.get("quote_data") if isinstance(state.get("quote_data"), dict) else {}
    market = state.get("market_data") if isinstance(state.get("market_data"), dict) else {}
    news = state.get("news")
    finance = (
        state.get("finance_data")
        if isinstance(state.get("finance_data"), dict)
        else None
    )
    errors = state.get("errors") or []

    name = intent.get("asset_name") or quote.get("name") or ""
    code = intent.get("asset_code") or quote.get("code") or market.get("code") or ""
    data_cutoff = quote.get("data_cutoff") or market.get("end_date")
    report_date = date.today().isoformat()

    meta_lines: list[str] = []
    if data_cutoff:
        meta_lines.append(f"数据截止：{data_cutoff}")
    meta_extra = ("\n".join(meta_lines) + "\n") if meta_lines else ""

    table_md = (quote.get("core_overview_md") or "").strip()
    if table_md:
        section_one = f"## 一、核心数据概览\n\n{table_md}\n\n"
    else:
        section_one = ""

    news_section_md = format_news_section_md(news if isinstance(news, list) else None)
    finance_periods = (finance or {}).get("periods") if finance else None
    finance_section_md = format_finance_section_md(
        finance_periods if isinstance(finance_periods, list) else None
    )

    market_for_llm = {
        "code": market.get("code"),
        "start_date": market.get("start_date"),
        "end_date": market.get("end_date"),
        "period_pct": market.get("period_pct"),
        "first_close": market.get("first_close"),
        "last_close": market.get("last_close"),
        "bar_count": market.get("bar_count"),
        "bars": (market.get("bars") or [])[-8:],
        "range_52w": market.get("range_52w"),
        "source": market.get("source"),
    }

    payload = {
        "asset_name": name,
        "asset_code": code,
        "report_date": report_date,
        "data_cutoff": data_cutoff,
        "quote_data": {
            "core_overview": quote.get("core_overview"),
            "source": quote.get("source"),
        },
        "window": {
            "start": market.get("start_date"),
            "end": market.get("end_date"),
            "note": "自然日近30天",
        },
        "market_data": market_for_llm,
        "errors": errors,
    }

    system = _SYSTEM_TEMPLATE.format(
        asset_name=name or "未知标的",
        asset_code=code or "------",
        report_date=report_date,
        meta_extra=meta_extra,
        section_one=section_one,
        section_news=news_section_md,
        section_finance=finance_section_md,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, default=str),
        },
    ]
    return None, messages, table_md, news_section_md, finance_section_md


def finalize_writer_body(
    body: str,
    table_md: str,
    news_section_md: str = "",
    finance_section_md: str = "",
) -> str:
    """模型正文后处理：空兜底、补核心表；资讯/财务段以系统生成版为准。"""
    text = (body or "").strip() or "数据不足，未能生成报告。"
    if table_md and "## 一、核心数据概览" not in text:
        text = _inject_core_table(text, table_md)
    if news_section_md:
        text = _replace_or_inject_news_section(text, news_section_md)
    if finance_section_md:
        text = _replace_or_inject_finance_section(text, finance_section_md)
    return text


def append_disclaimer(body: str) -> str:
    """追加免责声明（若尚无）。"""
    text = (body or "").rstrip()
    if "免责声明" not in text and "不构成" not in text:
        text = text + DISCLAIMER
    return text


def iter_writer_deltas(state: dict) -> Iterator[str]:
    """流式产出 Writer 正文增量（不含免责声明）。

    硬编码路径一次 yield 全文；LLM 路径逐 token yield，
    末尾若需补核心表 / 资讯 / 财务段则再 yield 后缀差分。
    """
    hardcoded, messages, table_md, news_section_md, finance_section_md = prepare_writer(
        state
    )
    if hardcoded is not None:
        yield hardcoded
        return

    assert messages is not None
    parts: list[str] = []
    for chunk in chat_completion_stream(messages):
        parts.append(chunk)
        yield chunk
    raw = "".join(parts)
    finalized = finalize_writer_body(
        raw, table_md, news_section_md, finance_section_md
    )
    if finalized.startswith(raw):
        suffix = finalized[len(raw) :]
        if suffix:
            yield suffix
    elif finalized != raw:
        if len(finalized) > len(raw):
            yield finalized[len(raw) :]


def _inject_core_table(body: str, table_md: str) -> str:
    """若模型漏写核心表，插到「二、股价走势分析」之前或文首。"""
    block = f"## 一、核心数据概览\n\n{table_md}\n\n"
    marker = "## 二、股价走势分析"
    if marker in body:
        return body.replace(marker, block + marker, 1)
    return block + body


def _replace_or_inject_news_section(body: str, news_section_md: str) -> str:
    """用系统生成的资讯段覆盖模型输出，保证 Markdown 链接可点。"""
    pattern = re.compile(
        r"##\s*三[、.．]?\s*资讯要点\s*\n.*?(?=\n##\s*[四五]|\Z)",
        re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(news_section_md.rstrip() + "\n\n", body, count=1)
    for marker in ("## 四、财务要点", "## 五、简要结论", "## 四、简要结论"):
        if marker in body:
            return body.replace(marker, news_section_md + marker, 1)
    return body.rstrip() + "\n\n" + news_section_md


def _replace_or_inject_finance_section(body: str, finance_section_md: str) -> str:
    """用系统生成的财务要点表覆盖模型输出。"""
    pattern = re.compile(
        r"##\s*四[、.．]?\s*财务要点\s*\n.*?(?=\n##\s*五|\Z)",
        re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(finance_section_md.rstrip() + "\n\n", body, count=1)
    for marker in ("## 五、简要结论", "## 四、简要结论"):
        if marker in body:
            return body.replace(marker, finance_section_md + marker, 1)
    return body.rstrip() + "\n\n" + finance_section_md
