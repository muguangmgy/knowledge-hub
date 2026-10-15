from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.agent.agents.coordinator import coordinator_node
from app.agent.agents.mailer import mailer_node
from app.agent.agents.market_analyst import market_analyst_node
from app.agent.agents.news_analyst import news_analyst_node
from app.agent.agents.quote_analyst import quote_analyst_node
from app.agent.agents.writer import append_disclaimer, iter_writer_deltas, prepare_writer
from app.common.config import get_settings
from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)

HEARTBEAT_SEC = 15.0

_STAGE_MSG = {
    "coordinator": "正在解析投研意图…",
    "quote": "正在拉取行情…",
    "market": "正在分析走势…",
    "news": "正在整理资讯…",
    "writer": "正在撰写报告…",
    "mailer": "正在处理邮件投递…",
}


def iter_research_stream(
    user_input: str,
    *,
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """增量投研：yield stage/delta/ping；成功 final；取消 cancelled。

    不落库；仅未取消时执行 Mailer。闸门语义与同步路径对齐。
    """
    settings = get_settings()
    timeout_sec = max(1, int(settings.RESEARCH_GRAPH_TIMEOUT_SEC or 90))
    deadline_ts = time.time() + timeout_sec
    t0 = time.perf_counter()

    state: dict[str, Any] = {
        "user_input": user_input,
        "intent": {},
        "skip_analysts": True,
        "deadline_ts": deadline_ts,
        "quote_data": None,
        "market_data": None,
        "news": None,
        "report_md": "",
        "errors": [],
        "timed_out": False,
        "delivery_status": "",
    }

    yield _stage("coordinator")
    if should_cancel():
        yield {"event": "cancelled"}
        return

    for ev in _run_node_with_heartbeat(
        lambda: coordinator_node(state), should_cancel
    ):
        if ev.get("event") in ("ping", "cancelled"):
            yield ev
            if ev.get("event") == "cancelled":
                return
            continue
        state.update(ev.get("data") or {})
        break

    if _past_deadline(state):
        state["timed_out"] = True

    if should_cancel():
        yield {"event": "cancelled"}
        return

    if not state.get("skip_analysts") and not state.get("timed_out"):
        for ev in _run_analysts_parallel(state, should_cancel):
            yield ev
            if ev.get("event") == "cancelled":
                return
        if _past_deadline(state):
            state["timed_out"] = True

    if should_cancel():
        yield {"event": "cancelled"}
        return

    if _past_deadline(state):
        state["timed_out"] = True

    yield _stage("writer")
    if should_cancel():
        yield {"event": "cancelled"}
        return

    hardcoded, _messages, _table = prepare_writer(state)
    body_parts: list[str] = []
    for chunk in iter_writer_deltas(state):
        if should_cancel():
            yield {"event": "cancelled"}
            return
        body_parts.append(chunk)
        yield {"event": "delta", "data": {"text": chunk}}

    report_body = "".join(body_parts)
    # 硬编码路径（超时/无标的）不加免责声明，与同步 Writer 一致
    pre_mail = report_body if hardcoded is not None else append_disclaimer(report_body)

    if should_cancel():
        yield {"event": "cancelled"}
        return

    skip_mail_hint = bool(state.get("timed_out") or state.get("skip_analysts"))
    yield _stage(
        "mailer",
        message="已跳过发送…" if skip_mail_hint else _STAGE_MSG["mailer"],
    )
    if should_cancel():
        yield {"event": "cancelled"}
        return

    state["report_md"] = pre_mail
    for ev in _run_node_with_heartbeat(lambda: mailer_node(state), should_cancel):
        if ev.get("event") in ("ping", "cancelled"):
            yield ev
            if ev.get("event") == "cancelled":
                return
            continue
        state.update(ev.get("data") or {})
        break

    final_report = (state.get("report_md") or pre_mail).strip()
    if final_report.startswith(report_body):
        suffix = final_report[len(report_body) :]
        if suffix:
            yield {"event": "delta", "data": {"text": suffix}}

    out = {
        "report_md": final_report or "分析未生成内容。\n\n未发送邮件。",
        "delivery_status": state.get("delivery_status") or "",
        "timed_out": bool(state.get("timed_out")),
    }
    intent = state.get("intent") or {}
    logger.info(
        event_msg(
            "research.stream_done",
            code=intent.get("asset_code") or "-",
            skip_analysts=bool(state.get("skip_analysts")),
            timed_out=out["timed_out"],
            delivery=out["delivery_status"] or "-",
            errors=len(state.get("errors") or []),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
        )
    )
    yield {"event": "final", "data": out}


def _stage(name: str, message: str | None = None) -> dict[str, Any]:
    """组装 stage 事件；message 缺省用内置中文文案。"""
    return {
        "event": "stage",
        "data": {"stage": name, "message": message or _STAGE_MSG.get(name, name)},
    }


def _past_deadline(state: dict) -> bool:
    """是否已超过 state.deadline_ts。"""
    ts = state.get("deadline_ts")
    return bool(ts and time.time() > float(ts))


def _run_node_with_heartbeat(
    fn: Callable[[], dict],
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """在工作线程跑节点；等待期间定期 yield ping；完成 yield _result。"""
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        while True:
            if should_cancel():
                yield {"event": "cancelled"}
                return
            try:
                patch = fut.result(timeout=HEARTBEAT_SEC)
                yield {"event": "_result", "data": patch}
                return
            except FuturesTimeoutError:
                yield {"event": "ping"}


def _run_analysts_parallel(
    state: dict[str, Any],
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """并行跑 quote/market/news；每路完成推对应 stage，空闲时 ping。"""
    jobs = {
        "quote": quote_analyst_node,
        "market": market_analyst_node,
        "news": news_analyst_node,
    }
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {name: ex.submit(fn, state) for name, fn in jobs.items()}
        pending = set(futs.keys())
        while pending:
            if should_cancel():
                yield {"event": "cancelled"}
                return
            if _past_deadline(state):
                state["timed_out"] = True
                return
            done_any = False
            for name in list(pending):
                fut = futs[name]
                if not fut.done():
                    continue
                pending.discard(name)
                done_any = True
                try:
                    patch = fut.result() or {}
                except Exception as exc:
                    patch = {"errors": [f"{name}: {exc}"]}
                if "errors" in patch:
                    errs = list(state.get("errors") or [])
                    errs.extend(patch.get("errors") or [])
                    patch = {**patch, "errors": errs}
                state.update(patch)
                yield _stage(name)
            if not done_any:
                yield {"event": "ping"}
                time.sleep(min(1.0, HEARTBEAT_SEC))
