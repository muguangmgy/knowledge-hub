from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.qq.com/",
}


def code6(code: str) -> str:
    """去掉市场前缀，规范为 6 位数字代码。"""
    c = (code or "").strip().lower()
    for p in ("sh", "sz", "bj"):
        if c.startswith(p):
            c = c[len(p) :]
    return c.zfill(6) if c.isdigit() else c


def prefixed(code: str) -> str:
    """按代码规则加 sh/sz/bj 前缀，供腾讯接口使用。"""
    c = code6(code)
    if c.startswith("6"):
        return f"sh{c}"
    if c.startswith(("0", "3")):
        return f"sz{c}"
    if c.startswith(("4", "8")):
        return f"bj{c}"
    return f"sh{c}"


def fetch_tencent_quote(code: str) -> dict[str, Any] | None:
    """腾讯 qt.gtimg.cn 单票基础字段（核心概览用）。"""
    pref = prefixed(code)
    url = f"https://qt.gtimg.cn/q={pref}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=8, headers=_HEADERS)
            resp.encoding = "gbk"
            text = (resp.text or "").strip()
            if '="' not in text:
                raise RuntimeError(f"unexpected payload: {text[:80]}")
            raw = text.split('="', 1)[1]
            if raw.endswith('";'):
                raw = raw[:-2]
            elif raw.endswith('"'):
                raw = raw[:-1]
            p = raw.split("~")
            if len(p) < 50:
                raise RuntimeError(f"too few fields: {len(p)}")

            def at(i: int) -> str:
                """按索引取腾讯 ~ 分隔字段；越界返回空串。"""
                return p[i].strip() if i < len(p) else ""

            price = _num(at(3))
            total_yi = _num(at(45))
            float_yi = _num(at(44))
            ts = at(30)
            quote_time = None
            if len(ts) >= 14 and ts.isdigit():
                quote_time = (
                    f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} "
                    f"{ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
                )
            return {
                "name": _str(at(1)),
                "code": code6(code),
                "price": price,
                "prev_close": _num(at(4)),
                "change_pct": _num(at(32)),
                "change_amount": _num(at(31)),
                "open": _num(at(5)),
                "high": _num(at(33)),
                "low": _num(at(34)),
                "volume": _num(at(6)) or _num(at(36)),
                "volume_unit": "手",
                "turnover_rate": _num(at(38)),
                "volume_ratio": _num(at(49)),
                "pe_dynamic": _num(at(39)),
                "pb": _num(at(46)),
                "market_cap_yi": total_yi,
                "float_market_cap_yi": float_yi,
                "market_cap": total_yi * 1e8 if total_yi is not None else None,
                "float_market_cap": float_yi * 1e8 if float_yi is not None else None,
                "high_52w": _num(at(67)) if len(p) > 67 else None,
                "low_52w": _num(at(68)) if len(p) > 68 else None,
                "quote_time": quote_time,
                "source": "tencent_gtimg",
            }
        except Exception:
            time.sleep(0.35 * (attempt + 1))
    return None


def fetch_tencent_kline(
    *,
    code: str,
    start: date | None = None,
    end: date | None = None,
    count: int = 320,
) -> list[dict[str, Any]]:
    """腾讯 fqkline 日 K（前复权）；解析时按「开/收/高/低」映射到 dict。"""
    end_d = end or date.today()
    start_d = start or (end_d - timedelta(days=30))
    pref = prefixed(code)
    start_s = start_d.isoformat()
    end_s = end_d.isoformat()
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={pref},day,{start_s},{end_s},{count},qfq"
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10, headers=_HEADERS)
            payload = resp.json()
            if payload.get("code") not in (0, "0", None):
                # code=0 正常；部分响应无 code
                if payload.get("data") is None:
                    raise RuntimeError(payload.get("msg") or "kline error")
            node = (payload.get("data") or {}).get(pref) or {}
            raw_rows = node.get("qfqday") or node.get("day") or node.get("hfqday") or []
            bars: list[dict[str, Any]] = []
            for row in raw_rows:
                if not isinstance(row, (list, tuple)) or len(row) < 6:
                    continue
                bars.append(
                    {
                        "date": str(row[0]),
                        "open": _num(row[1]),
                        "close": _num(row[2]),
                        "high": _num(row[3]),
                        "low": _num(row[4]),
                        "volume": _num(row[5]),  # 手
                    }
                )
            # 按请求窗口再滤一层
            bars = [b for b in bars if start_s <= b["date"] <= end_s]
            return bars
        except Exception as exc:
            last_err = exc
            time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"tencent kline failed code={code}: {last_err}")


def fetch_tencent_news(*, code: str, limit: int = 10, news_type: int = 1) -> list[dict[str, Any]]:
    """腾讯个股资讯 search 接口。"""
    pref = prefixed(code)
    url = (
        "https://web.ifzq.gtimg.cn/appstock/news/info/search"
        f"?page=1&symbol={pref}&n={max(1, min(limit, 30))}&type={news_type}"
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=10, headers=_HEADERS)
            payload = resp.json()
            if payload.get("code") not in (0, "0"):
                raise RuntimeError(payload.get("msg") or f"news code={payload.get('code')}")
            data = payload.get("data") or {}
            items = data.get("data") if isinstance(data, dict) else data
            if not isinstance(items, list):
                return []
            out: list[dict[str, Any]] = []
            for it in items[:limit]:
                if not isinstance(it, dict):
                    continue
                out.append(
                    {
                        "title": _str(it.get("title")) or "",
                        "time": _str(it.get("time") or it.get("create_time")) or "",
                        "summary": _str(it.get("summary")) or "",
                        "url": _str(it.get("url")) or "",
                        "source": _str(it.get("src") or it.get("typeStr")) or "腾讯财经",
                        "symbol": pref,
                    }
                )
            return out
        except Exception as exc:
            last_err = exc
            time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"tencent news failed code={code}: {last_err}")


def build_quote_bundle(code: str) -> dict[str, Any]:
    """基础字段节点产物：spot + 核心表 Markdown。"""
    spot = fetch_tencent_quote(code)
    overview = _build_core_overview(spot)
    rows = _core_overview_rows(overview)
    return {
        "code": code6(code),
        "name": (spot or {}).get("name"),
        "spot": spot,
        "core_overview": overview,
        "core_overview_rows": rows,
        "core_overview_md": _core_overview_table_md(rows),
        "data_cutoff": (spot or {}).get("quote_time"),
        "source": "tencent_gtimg",
    }


def build_market_bundle(*, code: str, end: date | None = None) -> dict[str, Any]:
    """走势节点产物：近 30 日 + 52 周高低（均直连腾讯 K 线）。"""
    end_d = end or date.today()
    start_d = end_d - timedelta(days=30)
    year_start = end_d - timedelta(days=370)

    bars_30 = fetch_tencent_kline(code=code, start=start_d, end=end_d, count=80)
    bars_52: list[dict[str, Any]] = []
    try:
        bars_52 = fetch_tencent_kline(code=code, start=year_start, end=end_d, count=320)
    except Exception:
        bars_52 = []

    first = bars_30[0] if bars_30 else {}
    last = bars_30[-1] if bars_30 else {}
    first_close = first.get("close")
    last_close = last.get("close")
    period_pct = None
    if isinstance(first_close, (int, float)) and isinstance(last_close, (int, float)) and first_close:
        period_pct = round((last_close - first_close) / first_close * 100, 2)

    range_52w = None
    if bars_52:
        highs = [b["high"] for b in bars_52 if isinstance(b.get("high"), (int, float))]
        lows = [b["low"] for b in bars_52 if isinstance(b.get("low"), (int, float))]
        if highs and lows:
            hi = max(highs)
            lo = min(lows)
            hi_date = next((b["date"] for b in bars_52 if b.get("high") == hi), None)
            lo_date = next((b["date"] for b in bars_52 if b.get("low") == lo), None)
            range_52w = {
                "high": hi,
                "low": lo,
                "high_date": hi_date,
                "low_date": lo_date,
            }

    return {
        "code": code6(code),
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "bars": bars_30[-15:],
        "bar_count": len(bars_30),
        "first_close": first_close,
        "last_close": last_close,
        "period_pct": period_pct,
        "range_52w": range_52w,
        "source": "tencent_fqkline",
    }


def _build_core_overview(spot: dict | None) -> dict[str, Any]:
    """把腾讯快照字段收成核心概览 dict（供表格与 Writer）。"""
    if not spot:
        return {}
    high_52 = spot.get("high_52w")
    low_52 = spot.get("low_52w")
    range_52w = None
    if high_52 is not None and low_52 is not None:
        range_52w = f"{low_52} ~ {high_52}"
    high, low = spot.get("high"), spot.get("low")
    return {
        "current_price": spot.get("price"),
        "prev_close": spot.get("prev_close"),
        "change_pct": spot.get("change_pct"),
        "change_amount": spot.get("change_amount"),
        "open": spot.get("open"),
        "high": high,
        "low": low,
        "high_low": f"{high} / {low}" if high is not None and low is not None else None,
        "volume": spot.get("volume"),
        "volume_unit": spot.get("volume_unit"),
        "volume_ratio": spot.get("volume_ratio"),
        "market_cap_yi": spot.get("market_cap_yi"),
        "float_market_cap_yi": spot.get("float_market_cap_yi"),
        "pe_dynamic": spot.get("pe_dynamic"),
        "pb": spot.get("pb"),
        "turnover_rate": spot.get("turnover_rate"),
        "range_52w": range_52w,
        "range_52w_high": high_52,
        "range_52w_low": low_52,
        "spot_source": spot.get("source"),
    }


def _core_overview_rows(overview: dict[str, Any] | None) -> list[dict[str, str]]:
    """四列表：指标 | 数值 | 变动情况 | 备注（备注用行情可算字段，无则该行不输出空列占位）。"""
    if not overview:
        return []
    rows: list[dict[str, str]] = []

    def add(metric: str, value: str | None, change: str = "", note: str = "") -> None:
        """追加一行概览；值为空则跳过。"""
        if value is None or str(value).strip() == "":
            return
        rows.append(
            {
                "metric": metric,
                "value": str(value).strip(),
                "change": (change or "").strip(),
                "note": (note or "").strip(),
            }
        )

    price = overview.get("current_price")
    chg = overview.get("change_pct")
    amt = overview.get("change_amount")
    if price is not None:
        chg_cell = ""
        if isinstance(chg, (int, float)):
            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "")
            chg_cell = f"{arrow} {chg:+.2f}%".strip()
        note = ""
        if isinstance(amt, (int, float)):
            direction = "上涨" if amt > 0 else ("下跌" if amt < 0 else "持平")
            note = f"较前日{direction} {abs(amt):.2f} 元"
        add("当前股价", f"{price}元", chg_cell, note)

    open_ = overview.get("open")
    if open_ is not None:
        note = "今日开盘"
        prev = overview.get("prev_close")
        if isinstance(prev, (int, float)) and prev:
            gap = (open_ - prev) / prev * 100
            note = f"相对昨收 {gap:+.2f}%"
        add("开盘价", f"{open_}元", "", note)

    high, low = overview.get("high"), overview.get("low")
    if high is not None and low is not None:
        note = ""
        base = overview.get("prev_close") or open_
        if isinstance(base, (int, float)) and base:
            amp = (high - low) / base * 100
            note = f"日内振幅 {amp:.2f}%"
        add("最高/最低价", f"{high} / {low}元", "", note)

    vol = overview.get("volume")
    if vol is not None:
        unit = overview.get("volume_unit") or "手"
        turnover = overview.get("turnover_rate")
        note = f"换手率 {turnover}%" if isinstance(turnover, (int, float)) else ""
        add("成交量", f"{vol}{unit}", "", note)

    vr = overview.get("volume_ratio")
    if vr is not None:
        if isinstance(vr, (int, float)):
            if vr < 0.8:
                note = "成交相对偏弱"
            elif vr > 1.2:
                note = "成交相对活跃"
            else:
                note = "成交大致持平"
        else:
            note = ""
        add("量比", str(vr), "", note)

    mcap = overview.get("market_cap_yi")
    if mcap is not None:
        fcap = overview.get("float_market_cap_yi")
        note = f"流通市值约 {fcap} 亿" if isinstance(fcap, (int, float)) else ""
        add("总市值", f"{mcap}亿元", "", note)

    pe = overview.get("pe_dynamic")
    if pe is not None:
        if isinstance(pe, (int, float)) and pe < 0:
            add("市盈率（动态）", f"{pe}倍", "亏损", "负值表示净利润为负")
        else:
            add("市盈率（动态）", f"{pe}倍")

    pb = overview.get("pb")
    if pb is not None:
        add("市净率（PB）", f"{pb}倍")

    hi52 = overview.get("range_52w_high")
    lo52 = overview.get("range_52w_low")
    if overview.get("range_52w"):
        note = ""
        if (
            isinstance(price, (int, float))
            and isinstance(hi52, (int, float))
            and isinstance(lo52, (int, float))
            and hi52 > lo52
        ):
            pos = (price - lo52) / (hi52 - lo52)
            if pos <= 0.33:
                note = "当前处于区间偏低位置"
            elif pos >= 0.67:
                note = "当前处于区间偏高位置"
            else:
                note = "当前处于区间中部震荡"
        add("52周区间", str(overview["range_52w"]), "", note)

    return rows


def _core_overview_table_md(rows: list[dict[str, str]]) -> str:
    """把概览行渲成 Markdown 表（有变动/备注用四列，否则两列）。"""
    if not rows:
        return ""
    # 有变动或备注时用四列；否则退化为两列
    use_extra = any(r.get("change") or r.get("note") for r in rows)
    if not use_extra:
        lines = ["| 指标 | 数值 |", "| --- | --- |"]
        for r in rows:
            lines.append(f"| {r['metric']} | {r['value']} |")
        return "\n".join(lines)

    lines = [
        "| 指标 | 数值 | 变动情况 | 备注 |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        change = r.get("change") or "—"
        note = r.get("note") or "—"
        lines.append(f"| {r['metric']} | {r['value']} | {change} | {note} |")
    return "\n".join(lines)


def _num(v: Any) -> float | None:
    """宽松解析数值；空串/占位符返回 None。"""
    try:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if s in ("", "-", "—", "None", "nan", "NaN", "{}"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> str | None:
    """转字符串并去空白；空则 None。"""
    if v is None:
        return None
    s = str(v).strip()
    return s or None
