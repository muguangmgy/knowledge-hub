"""投研 LangGraph：Coordinator 后按 route 走重投研、轻投研或闲聊。"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agent.agents.chat import chat_node
from app.agent.agents.coordinator import coordinator_node
from app.agent.agents.finance_analyst import finance_analyst_node
from app.agent.agents.light_answer import light_answer_node
from app.agent.agents.lookup import lookup_node
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

_Branch = Literal[
    "quote_analyst",
    "market_analyst",
    "news_analyst",
    "finance_analyst",
    "lookup",
    "chat",
]


def _route_after_coordinator(state: ResearchState) -> list[_Branch]:
    """重投研扇出四路；轻投研走 Lookup；其余走闲聊。"""
    route = state.get("route") or "chat"
    if route == "heavy_research":
        return ["quote_analyst", "market_analyst", "news_analyst", "finance_analyst"]
    if route == "light_research":
        return ["lookup"]
    return ["chat"]


def _build_graph():
    """编译三档条件边；四路 Analyst 经 list barrier 汇合后再进 Writer。"""
    g = StateGraph(ResearchState)
    g.add_node("coordinator", coordinator_node)
    g.add_node("quote_analyst", quote_analyst_node)
    g.add_node("market_analyst", market_analyst_node)
    g.add_node("news_analyst", news_analyst_node)
    g.add_node("finance_analyst", finance_analyst_node)
    g.add_node("writer", writer_node)
    g.add_node("mailer", mailer_node)
    g.add_node("lookup", lookup_node)
    g.add_node("light_answer", light_answer_node)
    g.add_node("chat", chat_node)

    g.add_edge(START, "coordinator")
    g.add_conditional_edges(
        "coordinator",
        _route_after_coordinator,
        [
            "quote_analyst",
            "market_analyst",
            "news_analyst",
            "finance_analyst",
            "lookup",
            "chat",
        ],
    )
    # 显式 barrier：等四路全部完成再调度 Writer（仅 heavy_research）
    g.add_edge(
        ["quote_analyst", "market_analyst", "news_analyst", "finance_analyst"],
        "writer",
    )
    g.add_edge("writer", "mailer")
    g.add_edge("mailer", END)
    # 轻投研与闲聊各自收口，不经过 Writer / Mailer
    g.add_edge("lookup", "light_answer")
    g.add_edge("light_answer", END)
    g.add_edge("chat", END)
    return g.compile()


def get_compiled_graph():
    """懒编译并缓存 LangGraph；进程内复用。"""
    global _compiled
    if _compiled is None:
        _compiled = _build_graph()
    return _compiled


def run_research_graph(
    user_input: str,
    *,
    conversation_id: int | None = None,
    history_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """同步执行投研 Multi-Agent 图；必须含外层线程池超时兜底。

    conversation_id 用来读写会话标的槽；history_messages 只给闲聊档。
    """
    settings = get_settings()
    timeout_sec = max(1, int(settings.RESEARCH_GRAPH_TIMEOUT_SEC or 90))
    initial: ResearchState = {
        "user_input": user_input,
        "route": "chat",
        "conversation_id": conversation_id,
        "history_messages": list(history_messages or []),
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
                "route": "",
            }

    out = {
        "report_md": (final.get("report_md") or "").strip()
        or "分析未生成内容。\n\n未发送邮件。",
        "delivery_status": final.get("delivery_status") or "",
        "timed_out": bool(final.get("timed_out")),
        "route": final.get("route") or "",
    }
    intent = final.get("intent") or {}
    logger.info(
        event_msg(
            "research.done",
            route=out["route"] or "-",
            code=intent.get("asset_code") or "-",
            skip_analysts=bool(final.get("skip_analysts")),
            timed_out=out["timed_out"],
            delivery=out["delivery_status"] or "-",
            errors=len(final.get("errors") or []),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    return out
