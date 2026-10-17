"""A 股代码表：新浪列表缓存到 Redis，并从原文抽出唯一标的。"""

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
# (id(table), alias rows)；alias 为证券全称，或「地名/中国 + 唯一简称」
_alias_for_id: tuple[int, list[tuple[str, str, str]]] | None = None

# 只剥这些前缀，避免「卓创资讯」把「资讯」收成简称
_REGION_PREFIXES = frozenset(
    {
        "贵州", "中国", "上海", "北京", "深圳", "广州", "江苏", "浙江", "山东",
        "四川", "重庆", "天津", "南京", "杭州", "宁波", "厦门", "青岛", "大连",
        "武汉", "长沙", "郑州", "合肥", "福州", "西安", "成都", "昆明", "海南",
        "河北", "河南", "湖北", "湖南", "安徽", "江西", "福建", "辽宁", "吉林",
        "山西", "陕西", "甘肃", "云南", "广西", "西藏", "新疆", "宁夏", "青海",
        "泸州", "宜宾",
    }
)
# 剥前缀后仍像日常用语的，不收成简称
_GENERIC_SHORTS = frozenset(
    {
        "资讯", "文化", "机场", "银行", "股份", "科技", "集团", "证券", "发展",
        "投资", "控股", "医药", "电力", "能源", "汽车", "食品", "材料", "电子",
        "生物", "信息", "数据", "传媒", "建设", "地产", "国际", "实业", "工业",
        "化工", "网络", "软件", "环保", "智能", "新材", "光电", "通信", "财务",
        "行情", "分析", "报告", "现价", "邮件", "对比", "高速", "港务", "水务",
    }
)


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
                return {"code": c, "name": _compact_name(n) or n}
        return None

    raw_name = _compact_name(name or "")
    if not raw_name:
        return None

    exact = [(c, n) for c, n in table if _compact_name(n) == raw_name]
    if len(exact) == 1:
        c, n = exact[0]
        return {"code": c, "name": _compact_name(n) or n}

    partial = [
        (c, n)
        for c, n in table
        if raw_name in _compact_name(n) or _compact_name(n) in raw_name
    ]
    if len(partial) == 1:
        c, n = partial[0]
        return {"code": c, "name": _compact_name(n) or n}
    return None


def _compact_name(name: str) -> str:
    """去掉简称里的空格（代码表里「五 粮 液」这类写法）。"""
    return re.sub(r"[\s\u3000]+", "", name or "")


def _alias_rows() -> list[tuple[str, str, str]]:
    """唯一别名表：(alias, code, canonical_name)，长名优先。

    收录证券全称。仅当全称以地名或「中国」开头、去掉该前缀后仍唯一，
    且不是「资讯」「股份」这类日常词时，才收简称（如「茅台」→ 贵州茅台）。
    """
    global _alias_for_id
    try:
        table = _a_share_table()
    except Exception:
        return []
    if _alias_for_id is not None and _alias_for_id[0] == id(table):
        return _alias_for_id[1]

    buckets: dict[str, set[tuple[str, str]]] = {}
    for code, name in table:
        if not name or len(name) < 2:
            continue
        buckets.setdefault(name, set()).add((code, name))
        compact = _compact_name(name)
        if compact and compact != name:
            buckets.setdefault(compact, set()).add((code, name))
        prefix, short = name[:2], name[2:]
        if (
            len(name) >= 4
            and prefix in _REGION_PREFIXES
            and len(short) >= 2
            and short not in _GENERIC_SHORTS
        ):
            buckets.setdefault(short, set()).add((code, name))

    rows = [
        (alias, code, name)
        for alias, pairs in buckets.items()
        if len(pairs) == 1
        for code, name in pairs
    ]
    rows.sort(key=lambda item: len(item[0]), reverse=True)
    _alias_for_id = (id(table), rows)
    return rows


def extract_symbols_from_text(text: str) -> list[dict]:
    """按原文出现顺序抽取全部有效 A 股；同一位置优先更长匹配。"""
    raw = (text or "").strip()
    if not raw:
        return []

    spans: list[tuple[int, int, str, str]] = []
    for alias, code, name in _alias_rows():
        start = 0
        while True:
            idx = raw.find(alias, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(alias), code, name))
            start = idx + 1

    for match in _CODE_IN_TEXT_RE.finditer(raw):
        hit = resolve_symbol(name=None, code=match.group(1))
        if hit:
            spans.append((match.start(1), match.end(1), hit["code"], hit["name"]))

    # 同一起点先留更长的别名；区间重叠的短匹配丢掉
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    picked: list[tuple[int, int, str, str]] = []
    for start, end, code, name in spans:
        if any(not (end <= prev_s or start >= prev_e) for prev_s, prev_e, _, _ in picked):
            continue
        picked.append((start, end, code, name))

    out: list[dict] = []
    seen: set[str] = set()
    for _, _, code, name in picked:
        if code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": _compact_name(name) or name})
    return out


def extract_symbol_from_text(text: str) -> dict | None:
    """从原文规则抽取第一只有效 A 股（代码或唯一简称）。"""
    hits = extract_symbols_from_text(text)
    return hits[0] if hits else None
