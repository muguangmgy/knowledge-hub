from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from app.agent.tools.tencent import code6

FINANCE_PERIODS = 4  # 报告写入最近 N 期
_FETCH_TIMEOUT_SEC = 20  # 单次拉数硬超时，避免卡住整图


def em_symbol(code: str) -> str:
    """6 位代码 → 东财/AKShare 格式（如 600519.SH）。"""
    c = code6(code)
    if c.startswith("6"):
        return f"{c}.SH"
    if c.startswith(("0", "3")):
        return f"{c}.SZ"
    if c.startswith(("4", "8")):
        return f"{c}.BJ"
    return f"{c}.SH"


def _yi(val: Any) -> str:
    """金额转「xx.xx亿」；无效则 —。"""
    try:
        if val is None:
            return "—"
        n = float(val)
        if n != n:  # NaN
            return "—"
        return f"{n / 1e8:.2f}亿"
    except (TypeError, ValueError):
        return "—"


def _pct(val: Any) -> str:
    """百分比保留两位；无效则 —。"""
    try:
        if val is None:
            return "—"
        n = float(val)
        if n != n:
            return "—"
        return f"{n:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fetch_indicator_rows(symbol: str, periods: int) -> list[dict[str, Any]]:
    """调用 AKShare 财务指标接口，取最近 N 个报告期。"""
    import akshare as ak

    df = ak.stock_financial_analysis_indicator_em(
        symbol=symbol, indicator="按报告期"
    )
    if df is None or getattr(df, "empty", True):
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.head(max(1, periods)).iterrows():
        rows.append(
            {
                "period": str(r.get("REPORT_DATE_NAME") or "").strip(),
                "report_date": str(r.get("REPORT_DATE") or "")[:10],
                "revenue": r.get("TOTALOPERATEREVE"),
                "revenue_yoy": r.get("TOTALOPERATEREVETZ"),
                "parent_net_profit": r.get("PARENTNETPROFIT"),
                "parent_net_profit_yoy": r.get("PARENTNETPROFITTZ"),
                "roe": r.get("ROEJQ"),
                "gross_margin": r.get("XSMLL"),
            }
        )
    return rows


def format_finance_section_md(periods: list[dict[str, Any]] | None) -> str:
    """格式化为「四、财务要点」Markdown 表。"""
    if not periods:
        return (
            "## 四、财务要点\n\n"
            "暂无可用财务指标（数据源暂时不可用）。\n\n"
        )
    lines = [
        "## 四、财务要点",
        "",
        "| 报告期 | 营业总收入 | 营收同比 | 归母净利润 | 归母同比 | ROE | 毛利率 |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for p in periods:
        lines.append(
            "| {period} | {rev} | {rev_yoy} | {np} | {np_yoy} | {roe} | {gm} |".format(
                period=p.get("period") or "—",
                rev=_yi(p.get("revenue")),
                rev_yoy=_pct(p.get("revenue_yoy")),
                np=_yi(p.get("parent_net_profit")),
                np_yoy=_pct(p.get("parent_net_profit_yoy")),
                roe=_pct(p.get("roe")),
                gm=_pct(p.get("gross_margin")),
            )
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def build_finance_bundle(code: str, *, periods: int = FINANCE_PERIODS) -> dict[str, Any]:
    """拉取最近若干报告期关键财务指标，供 FinanceAnalyst / Writer 使用。

    用线程池包一层 timeout：AKShare 同步调用偶发挂起时及时失败，由 Analyst 吞异常写 errors。
    """
    symbol = em_symbol(code)
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch_indicator_rows, symbol, periods)
        try:
            rows = fut.result(timeout=_FETCH_TIMEOUT_SEC)
        except FuturesTimeoutError as exc:
            raise RuntimeError(
                f"akshare finance timeout after {_FETCH_TIMEOUT_SEC}s"
            ) from exc
    if not rows:
        raise RuntimeError(f"akshare finance empty symbol={symbol}")
    return {
        "code": code6(code),
        "symbol": symbol,
        "periods": rows,
        "source": "eastmoney_akshare",
    }
