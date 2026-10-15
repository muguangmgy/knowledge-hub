from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agent.agents.coordinator import coordinator_node
from app.agent.agents.finance_analyst import finance_analyst_node
from app.agent.agents.mailer import mailer_node
from app.agent.agents.market_analyst import market_analyst_node
from app.agent.agents.news_analyst import news_analyst_node
from app.agent.agents.quote_analyst import quote_analyst_node
from app.agent.agents.writer import writer_node
from app.agent.state import ResearchState
from app.common.config import get_settings
from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)

_compiled = None

_Analyst = Literal[
    "quote_analyst",
    "market_analyst",
    "news_analyst",
    "finance_analyst",
    "writer",
]


def _route_after_coordinator(state: ResearchState) -> list[_Analyst]:
    """有标的扇出四路 Analyst；无标的短路到 Writer。"""
    if state.get("skip_analysts"):
        return ["writer"]
    return ["quote_analyst", "market_analyst", "news_analyst", "finance_analyst"]


def _build_graph():
    """编译固定边；四路 Analyst 均指向 Writer，由 LangGraph 汇合后再写报告。"""
    g = StateGraph(ResearchState)
    g.add_node("coordinator", coordinator_node)
    g.add_node("quote_analyst", quote_analyst_node)
    g.add_node("market_analyst", market_analyst_node)
    g.add_node("news_analyst", news_analyst_node)
    g.add_node("finance_analyst", finance_analyst_node)
    g.add_node("writer", writer_node)
    g.add_node("mailer", mailer_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        _route_after_coordinator,
        [
            "quote_analyst",
            "market_analyst",
            "news_analyst",
            "finance_analyst",
            "writer",
        ],
    )
    g.add_edge("quote_analyst", "writer")
    g.add_edge("market_analyst", "writer")
    g.add_edge("news_analyst", "writer")
    g.add_edge("finance_analyst", "writer")
    g.add_edge("writer", "mailer")
    g.add_edge("mailer", END)
    return g.compile()


def get_compiled_graph():
    """懒编译并缓存 LangGraph；进程内复用。"""
    global _compiled
    if _compiled is None:
        _compiled = _build_graph()
    return _compiled


def run_research_graph(user_input: str) -> dict[str, Any]:
    """同步执行投研 Multi-Agent 图；必须含外层线程池超时兜底。"""
    settings = get_settings()
    timeout_sec = max(1, int(settings.RESEARCH_GRAPH_TIMEOUT_SEC or 90))
    initial: ResearchState = {
        "user_input": user_input,
        "intent": {},
        "skip_analysts": True,
        "deadline_ts": time.time() + timeout_sec,
        "quote_data": None,
        "market_data": None,
        "news": None,
        "finance_data": None,
        "report_md": "",
        "errors": [],
        "timed_out": False,
        "delivery_status": "",
    }
    graph = get_compiled_graph()
    t0 = time.perf_counter()

    def _invoke():
        """在工作线程中同步 invoke，供外层超时兜底。"""
        return graph.invoke(initial)

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_invoke)
        try:
            final = fut.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            logger.warning(
                event_msg(
                    "research.timeout",
                    timeout_sec=timeout_sec,
                    elapsed_ms=int((time.perf_counter() - t0) * 1000),
                )
            )
            return {
                "report_md": "分析超时，请稍后重试。\n\n未发送邮件（超时）。",
                "delivery_status": "已跳过（超时）",
                "timed_out": True,
            }

    out = {
        "report_md": (final.get("report_md") or "").strip()
        or "分析未生成内容。\n\n未发送邮件。",
        "delivery_status": final.get("delivery_status") or "",
        "timed_out": bool(final.get("timed_out")),
    }
    intent = final.get("intent") or {}
    logger.info(
        event_msg(
            "research.done",
            code=intent.get("asset_code") or "-",
            skip_analysts=bool(final.get("skip_analysts")),
            timed_out=out["timed_out"],
            delivery=out["delivery_status"] or "-",
            errors=len(final.get("errors") or []),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    return out
