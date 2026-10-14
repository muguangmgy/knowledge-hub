from __future__ import annotations

import json
from datetime import date

from app.agent.logging_util import check_deadline
from app.llm.client import chat_completion

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

## 三、资讯要点

只写与标的**直接相关**的资讯，每条标注日期。
依据 JSON 中 `news`（腾讯个股资讯）撰写；若列表为空，写「暂无直接相关资讯」。
不要编造资讯。

## 四、简要结论

2~4 句话概括走势与关注点。

【硬性约束】
- 全文不超过 600 字（不含系统已给出的核心数据表）。
- 禁止编造任何数字；若已给出「一、核心数据概览」表格，须原样保留，不得增删行或改数，也勿再写「请原样保留」之类说明。
- 只输出报告正文，不要套代码块。
- 不要输出免责声明（由系统追加）。
"""


def writer_node(state: dict) -> dict:
    """综合三路数据写 Markdown；超时/无标的走硬编码；免责声明由系统追加。"""
    patch = check_deadline(state)
    timed_out = bool(state.get("timed_out") or patch.get("timed_out"))
    if timed_out:
        return {"timed_out": True, "report_md": TIMEOUT_MSG}

    if state.get("skip_analysts"):
        return {"report_md": NO_SYMBOL_MSG}

    intent = state.get("intent") or {}
    quote = state.get("quote_data") if isinstance(state.get("quote_data"), dict) else {}
    market = state.get("market_data") if isinstance(state.get("market_data"), dict) else {}
    news = state.get("news")
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
        "news": news,
        "errors": errors,
    }

    system = _SYSTEM_TEMPLATE.format(
        asset_name=name or "未知标的",
        asset_code=code or "------",
        report_date=report_date,
        meta_extra=meta_extra,
        section_one=section_one,
    )

    report = chat_completion(
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, default=str),
            },
        ]
    )
    body = (report or "").strip() or "数据不足，未能生成报告。"
    if table_md and "## 一、核心数据概览" not in body:
        body = _inject_core_table(body, table_md)
    if "免责声明" not in body and "不构成" not in body:
        body = body.rstrip() + DISCLAIMER
    return {"report_md": body}


def _inject_core_table(body: str, table_md: str) -> str:
    """若模型漏写核心表，插到「二、股价走势分析」之前或文首。"""
    block = f"## 一、核心数据概览\n\n{table_md}\n\n"
    marker = "## 二、股价走势分析"
    if marker in body:
        return body.replace(marker, block + marker, 1)
    return block + body
