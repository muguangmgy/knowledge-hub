from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    """投研 LangGraph 共享状态。

    errors 用 Annotated[..., operator.add]，以便多路 Analyst 并行时错误列表可合并。
    """

    # 用户本轮原话
    user_input: str
    # heavy_research | light_research | chat；条件边以它为准
    route: str
    # 会话 id，用于读写 Redis 标的槽；可空
    conversation_id: int | None
    # 最近最多 6 条 {role, content}；仅 chat 档拼进 prompt
    history_messages: list[dict[str, Any]]
    # Coordinator 解析：标的 / 发信 / 指代等
    intent: IntentState
    # 兼容字段：等价于 route != heavy_research（驱边以 route 为准）
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

class IntentState(TypedDict, total=False):
    """Coordinator 解析结果；键按节点逐步补齐。"""

    # 解析出的股票代码（如 sh600519）；未解析到则为 None
    asset_code: str | None
    # 标的名称；与 asset_code 成对写入
    asset_name: str | None
    # 用户是否要求把报告发邮件
    want_email: bool
    # 收件邮箱；可从原文或 LLM 解析得到
    to_email: str | None
    # 本轮是否在指代上一只股票（如「它」「这只」）
    continues_previous: bool
    # 需要澄清标的（缺码 / 会话无槽等）时走 chat 提示
    clarify_previous: bool
    # 提到了名称但未命中覆盖池时的原文名
    uncovered_name: str
    # 多标的对比等暂不支持场景，Writer 可据此提示
    compare_unsupported: bool
