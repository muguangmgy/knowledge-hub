from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    """投研 LangGraph 共享状态。

    errors 用 Annotated[..., operator.add]，以便多路 Analyst 并行时错误列表可合并。
    """

    # 用户本轮原话（不带闲聊历史）
    user_input: str
    # Coordinator 解析结果：asset_name / asset_code / want_email / to_email
    intent: dict[str, Any]
    # True=无有效标的，跳过 Analyst，Writer 走硬编码提示
    skip_analysts: bool
    # 图内截止 Unix 时间戳；超时后各节点跳过实际工作且禁止发信
    deadline_ts: float
    # QuoteAnalyst：腾讯快照 + 核心概览表（含 core_overview_md）
    quote_data: dict[str, Any] | None
    # MarketAnalyst：近 30 日日 K 摘要 + 52 周高低
    market_data: dict[str, Any] | None
    # NewsAnalyst：腾讯个股资讯列表
    news: list[dict[str, Any]] | None
    # FinanceAnalyst：AKShare 最近若干报告期关键财务指标
    finance_data: dict[str, Any] | None
    # Writer 产出的 Markdown 报告；Mailer 可在文末追加投递说明（不进 PDF）
    report_md: str
    # 非致命错误列表（并行 Analyst 可能同时 append，须用 operator.add 合并）
    errors: Annotated[list[str], operator.add]
    # True=已超时；Writer 写超时文案，Mailer 不发信
    timed_out: bool
    # 发信结果摘要（日志/调试；聊天侧主要看 report_md 文末说明）
    delivery_status: str
