from __future__ import annotations

import json
import re
import time

import requests

_CODE_RE = re.compile(r"^(?:sh|sz|bj)?(\d{6})$", re.I)
_CODE_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_REDIS_KEY = "kh:agent:a_share_symbols"
_REDIS_TTL_SEC = 60 * 60 * 24  # 24h

# 新浪行情中心节点（沪 A / 深 A / 创业板 / 科创板）
_SINA_NODES = ("sh_a", "sz_a", "cyb", "kcb")
_SINA_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn/",
}

_mem_table: list[tuple[str, str]] | None = None


def _fetch_a_share_list() -> list[tuple[str, str]]:
    """新浪节点分页拉取 A 股代码/简称（不依赖 akshare）。"""
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    page_size = 80

    for node in _SINA_NODES:
        page = 1
        while page <= 80:
            params = {
                "page": page,
                "num": page_size,
                "sort": "symbol",
                "asc": 1,
                "node": node,
                "symbol": "",
                "_s_r_a": "page",
            }
            batch = _sina_page(params)
            if not batch:
                break
            for item in batch:
                code = str(item.get("code") or "").strip()
                name = str(item.get("name") or "").strip()
                m = _CODE_RE.match(code)
                if not m or not name or code in seen:
                    continue
                seen.add(code)
                rows.append((m.group(1), name))
            if len(batch) < page_size:
                break
            page += 1
            time.sleep(0.05)
    return rows


def _sina_page(params: dict) -> list[dict]:
    """请求新浪行情中心单页列表；失败重试后抛错。"""
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(
                _SINA_URL, params=params, headers=_HEADERS, timeout=15
            )
            text = (resp.text or "").strip()
            if not text or text in ("null", "[]"):
                return []
            data = resp.json()
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            return []
        except Exception as exc:
            last_err = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"sina stock list failed: {last_err}")


def _load_from_redis() -> list[tuple[str, str]] | None:
    """从 Redis 读 A 股代码表缓存；未配置或失败返回 None。"""
    from app.common.redis_client import get_redis

    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        out: list[tuple[str, str]] = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((str(item[0]), str(item[1])))
        return out or None
    except Exception:
        return None


def _save_to_redis(rows: list[tuple[str, str]]) -> None:
    """把 A 股代码表写入 Redis（带 TTL）；失败静默忽略。"""
    from app.common.redis_client import get_redis

    client = get_redis()
    if client is None or not rows:
        return
    try:
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        client.setex(_REDIS_KEY, _REDIS_TTL_SEC, payload)
    except Exception:
        pass


def _a_share_table() -> list[tuple[str, str]]:
    """A 股列表：进程内存 → Redis → 新浪节点。"""
    global _mem_table
    if _mem_table is not None:
        return _mem_table

    cached = _load_from_redis()
    if cached is not None:
        _mem_table = cached
        return _mem_table

    rows = _fetch_a_share_list()
    _mem_table = rows
    if rows:
        _save_to_redis(rows)
    return _mem_table


def warm_symbol_cache() -> int:
    """启动预热：填满 Redis + 进程内存；返回条数。"""
    global _mem_table
    _mem_table = None
    return len(_a_share_table())


def resolve_symbol(*, name: str | None, code: str | None) -> dict | None:
    """校验/补全标的；成功返回 {code, name}，失败返回 None。"""
    try:
        table = _a_share_table()
    except Exception:
        return None

    raw_code = (code or "").strip()
    m = _CODE_RE.match(raw_code.replace(".", ""))
    if m:
        want = m.group(1)
        for c, n in table:
            if c == want:
                return {"code": c, "name": n}
        return None

    raw_name = (name or "").strip()
    if not raw_name:
        return None

    exact = [(c, n) for c, n in table if n == raw_name]
    if len(exact) == 1:
        c, n = exact[0]
        return {"code": c, "name": n}

    partial = [(c, n) for c, n in table if raw_name in n or n in raw_name]
    if len(partial) == 1:
        c, n = partial[0]
        return {"code": c, "name": n}
    return None


def extract_symbol_from_text(text: str) -> dict | None:
    """从原文规则抽取标的：先 6 位代码，再最长证券简称命中。"""
    raw = (text or "").strip()
    if not raw:
        return None

    m = _CODE_IN_TEXT_RE.search(raw)
    if m:
        hit = resolve_symbol(name=None, code=m.group(1))
        if hit:
            return hit

    try:
        table = _a_share_table()
    except Exception:
        return None

    ranked = sorted(
        ((c, n) for c, n in table if n and len(n) >= 2),
        key=lambda x: len(x[1]),
        reverse=True,
    )
    for code, name in ranked:
        if name in raw:
            return {"code": code, "name": name}
    return None
