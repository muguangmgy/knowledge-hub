"""投研 SSE：按 route 增量推 stage/delta，只有重投研才进 Mailer。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.agent.agents.chat import iter_chat_deltas
from app.agent.agents.coordinator import coordinator_node
from app.agent.agents.finance_analyst import finance_analyst_node
from app.agent.agents.light_answer import iter_light_deltas
from app.agent.agents.lookup import lookup_node
from app.agent.agents.mailer import mailer_node
from app.agent.agents.market_analyst import market_analyst_node
from app.agent.agents.news_analyst import news_analyst_node
from app.agent.agents.quote_analyst import quote_analyst_node
from app.agent.agents.writer import append_disclaimer, ensure_compare_note, iter_writer_deltas, prepare_writer
from app.common.config import get_settings
from app.common.logging_util import event_msg

logger = logging.getLogger(__name__)

# 单节点等待超过该秒数仍未完成 → yield ping，避免 SSE 空闲被代理掐断
HEARTBEAT_SEC = 15.0

# stage 事件默认中文文案（前端 stageMessage / 输入框提示条）
_STAGE_MSG = {
    "coordinator": "正在理解你的问题…",
    "quote": "正在拉取行情…",
    "market": "正在分析走势…",
    "news": "正在整理资讯…",
    "finance": "正在整理财务要点…",
    "writer": "正在撰写报告…",
    "mailer": "正在处理邮件投递…",
    "lookup": "正在查询行情与财务…",
    "light_answer": "正在整理回答…",
    "chat": "正在回复…",
}


def iter_research_stream(
    user_input: str,
    *,
    conversation_id: int | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """增量投研：yield stage/delta/ping；成功 final；取消 cancelled。

    不落库。仅 heavy 且未取消时执行 Mailer。闸门语义与同步路径对齐。
    """
    # --- 0. 截止时间 + 共享 state（与同步 run_research_graph 字段对齐）---
    settings = get_settings()
    timeout_sec = max(1, int(settings.RESEARCH_GRAPH_TIMEOUT_SEC or 90))
    deadline_ts = time.time() + timeout_sec
    t0 = time.perf_counter()

    state: dict[str, Any] = {
        "user_input": user_input,
        "route": "chat",
        "conversation_id": conversation_id,
        "history_messages": list(history_messages or []),
        "intent": {},
        "skip_analysts": True,
        "deadline_ts": deadline_ts,
        "quote_data": None,
        "market_data": None,
        "news": None,
        "finance_data": None,
        "report_md": "",
        "errors": [],
        "timed_out": False,
        "delivery_status": "",
    }

    # --- 1. Coordinator：先推 stage，再跑节点；结果 merge 进 state ---
    yield _stage("coordinator")
    if should_cancel():
        yield {"event": "cancelled"}
        return

    for ev in _run_node_with_heartbeat(
        lambda: coordinator_node(state), should_cancel
    ):
        # ping / cancelled 原样上抛；_result 的 patch 写回 state 后结束等待
        if ev.get("event") in ("ping", "cancelled"):
            yield ev
            if ev.get("event") == "cancelled":
                return
            continue
        state.update(ev.get("data") or {})  # 典型含 intent / route / skip_analysts
        break

    if _past_deadline(state):
        state["timed_out"] = True

    if should_cancel():
        yield {"event": "cancelled"}
        return

    route = state.get("route") or "chat"
    if route == "light_research":
        yield from _stream_light(state, should_cancel, t0)
        return
    if route != "heavy_research":
        yield from _stream_chat(state, should_cancel, t0)
        return

    # --- 2. 重投研：并行 Analyst；每路完成推 stage:quote|market|… ---
    if not state.get("timed_out"):
        for ev in _run_analysts_parallel(state, should_cancel):
            yield ev
            if ev.get("event") == "cancelled":
                return
        if _past_deadline(state):
            state["timed_out"] = True

    if should_cancel():
        yield {"event": "cancelled"}
        return

    # Writer 前再卡一次 deadline（Analyst 跳过时也要标记超时）
    if _past_deadline(state):
        state["timed_out"] = True

    # --- 3. Writer：流式 delta；超时/无标的走硬编码文案（hardcoded 非 None）---
    yield _stage("writer")
    if should_cancel():
        yield {"event": "cancelled"}
        return

    hardcoded, _messages, _table, _news, _fin = prepare_writer(state)
    body_parts: list[str] = []
    for chunk in iter_writer_deltas(state):
        if should_cancel():
            yield {"event": "cancelled"}
            return
        body_parts.append(chunk)
        yield {"event": "delta", "data": {"text": chunk}}

    raw_body = "".join(body_parts)
    report_body = raw_body if hardcoded is not None else ensure_compare_note(raw_body, state)
    # 硬编码路径（超时）不加免责声明，与同步 Writer 一致
    pre_mail = report_body if hardcoded is not None else append_disclaimer(report_body)

    if should_cancel():
        yield {"event": "cancelled"}
        return

    # --- 4. Mailer：仅重投研到达；取消则不发信；超时时 stage 文案改为「已跳过发送…」---
    skip_mail_hint = bool(state.get("timed_out"))
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
        # patch 可含 delivery_status，以及追加到 report_md 的投递说明
        state.update(ev.get("data") or {})
        break

    # 尚未推送给前端的后缀（对比说明 / 免责声明 / 投递说明）
    final_report = (state.get("report_md") or pre_mail).strip()
    if final_report.startswith(raw_body):
        suffix = final_report[len(raw_body) :]
        if suffix:
            yield {"event": "delta", "data": {"text": suffix}}

    yield from _yield_final(state, t0, fallback=final_report or "分析未生成内容。\n\n未发送邮件。")


def _stream_light(
    state: dict[str, Any],
    should_cancel: Callable[[], bool],
    t0: float,
) -> Iterator[dict[str, Any]]:
    """轻投研：Lookup → LightAnswer，不进入 Mailer。"""
    yield _stage("lookup")
    if should_cancel():
        yield {"event": "cancelled"}
        return
    if not state.get("timed_out"):
        for ev in _run_node_with_heartbeat(lambda: lookup_node(state), should_cancel):
            if ev.get("event") in ("ping", "cancelled"):
                yield ev
                if ev.get("event") == "cancelled":
                    return
                continue
            _merge_patch(state, ev.get("data") or {})
            break
    if _past_deadline(state):
        state["timed_out"] = True
    if should_cancel():
        yield {"event": "cancelled"}
        return

    yield _stage("light_answer")
    if should_cancel():
        yield {"event": "cancelled"}
        return
    parts: list[str] = []
    for chunk in iter_light_deltas(state):
        if should_cancel():
            yield {"event": "cancelled"}
            return
        parts.append(chunk)
        yield {"event": "delta", "data": {"text": chunk}}
    state["report_md"] = "".join(parts).strip()
    yield from _yield_final(state, t0, fallback=state["report_md"] or "暂时无法回答。")


def _stream_chat(
    state: dict[str, Any],
    should_cancel: Callable[[], bool],
    t0: float,
) -> Iterator[dict[str, Any]]:
    """闲聊：ChatNode，不拉数、不发信。"""
    yield _stage("chat")
    if should_cancel():
        yield {"event": "cancelled"}
        return
    parts: list[str] = []
    for chunk in iter_chat_deltas(state):
        if should_cancel():
            yield {"event": "cancelled"}
            return
        parts.append(chunk)
        yield {"event": "delta", "data": {"text": chunk}}
    state["report_md"] = "".join(parts).strip()
    yield from _yield_final(state, t0, fallback=state["report_md"] or "暂时无法回答。")


def _merge_patch(state: dict[str, Any], patch: dict) -> None:
    """合并节点补丁；errors 按追加语义累加。"""
    if "errors" in patch:
        errs = list(state.get("errors") or [])
        errs.extend(patch.get("errors") or [])
        patch = {**patch, "errors": errs}
    state.update(patch)


def _yield_final(
    state: dict[str, Any],
    t0: float,
    *,
    fallback: str,
) -> Iterator[dict[str, Any]]:
    """组装 final 并打 route 日志。"""
    out = {
        "report_md": (state.get("report_md") or fallback).strip() or fallback,
        "delivery_status": state.get("delivery_status") or "",
        "timed_out": bool(state.get("timed_out")),
        "route": state.get("route") or "",
    }
    intent = state.get("intent") or {}
    logger.info(
        event_msg(
            "research_stream",
            route=out["route"] or "-",
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
    # 形如 {"event":"stage","data":{"stage":"quote","message":"正在拉取行情…"}}
    return {
        "event": "stage",
        "data": {"stage": name, "message": message or _STAGE_MSG.get(name, name)},
    }


def _past_deadline(state: dict) -> bool:
    """是否已超过 state.deadline_ts。"""
    # deadline_ts 缺省/为 0 视为未设截止，不算超时
    ts = state.get("deadline_ts")
    return bool(ts and time.time() > float(ts))


def _run_node_with_heartbeat(
    fn: Callable[[], dict],
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """在工作线程跑节点；等待期间定期 yield ping；完成 yield _result。

    调用方应把 ``_result.data`` merge 进 state；ping/cancelled 原样上抛。
    ``_result`` 仅供本模块内部，chat/API 层不会写成 SSE。
    """
    # 单线程池：节点同步阻塞（HTTP/LLM）不占住生成器轮询
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        while True:
            # --- 取消优先：不再等节点返回 ---
            if should_cancel():
                yield {"event": "cancelled"}
                return
            try:
                # 最多等 HEARTBEAT_SEC；超时则抛 FuturesTimeoutError → ping
                patch = fut.result(timeout=HEARTBEAT_SEC)
                # 节点返回的 state patch（如 intent / report_md / delivery_status）
                yield {"event": "_result", "data": patch}
                return
            except FuturesTimeoutError:
                # 保活：API 会转成 SSE comment ``: ping``
                yield {"event": "ping"}


def _run_analysts_parallel(
    state: dict[str, Any],
    should_cancel: Callable[[], bool],
) -> Iterator[dict[str, Any]]:
    """并行跑 quote/market/news/finance；每路完成推对应 stage，空闲时 ping。

    四路共享同一 state 引用提交；完成一路立刻 merge + yield stage（顺序不保证）。
    超时则标 timed_out 并返回（不取消已在跑的 future，后续 Writer 走超时文案）。
    """
    # --- 1. 四路同时提交 ---
    jobs = {
        "quote": quote_analyst_node,
        "market": market_analyst_node,
        "news": news_analyst_node,
        "finance": finance_analyst_node,
    }
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {name: ex.submit(fn, state) for name, fn in jobs.items()}
        pending = set(futs.keys())
        while pending:
            # --- 2. 取消 / 全局 deadline 闸门 ---
            if should_cancel():
                yield {"event": "cancelled"}
                return
            if _past_deadline(state):
                state["timed_out"] = True
                return

            # --- 3. 收割已完成的 future，merge patch，推 stage ---
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
                    # 单路异常不中断其它路，记入 errors 供 Writer 降级
                    patch = {"errors": [f"{name}: {exc}"]}
                if "errors" in patch:
                    # 并行 merge：与 Annotated[list, operator.add] 语义对齐（手动累加）
                    errs = list(state.get("errors") or [])
                    errs.extend(patch.get("errors") or [])
                    patch = {**patch, "errors": errs}
                state.update(patch)
                yield _stage(name)  # stage 名即 quote|market|news|finance

            # --- 4. 本轮无人完成：ping + 短睡，避免空转打满 CPU ---
            if not done_any:
                yield {"event": "ping"}
                time.sleep(min(1.0, HEARTBEAT_SEC))
