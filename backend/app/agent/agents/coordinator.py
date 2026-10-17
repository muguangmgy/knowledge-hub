"""解析三档 route、标的与发信意图；规则优先，失败再 LLM 兜底。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.logging_util import check_deadline
from app.agent.tools.email import extract_email_from_text
from app.agent.tools.research_context import get_research_context, set_research_context
from app.agent.tools.symbol import extract_symbols_from_text, resolve_symbol
from app.llm.client import chat_completion

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_EMAIL_KEYWORDS = (
    "发到",
    "发至",
    "发送",
    "发我",
    "发邮件",
    "发邮箱",
    "邮箱",
    "邮件",
    "email",
    "mail",
)
_HEAVY_RE = re.compile(
    r"研报|研究报告|深度分析|深度(?!睡眠|学习|优先|思考)|对比|比较|近日行情|走势分析|生成报告|写报告|出报告"
)
_COMPARE_RE = re.compile(r"对比|比较")
# 「其它」里的它、「这只是闲聊」不算续指；「它们」「这只呢」「这只是不是太贵」仍算
_CONTINUE_RE = re.compile(
    r"(?<!其)它"
    r"|这只(?!是(?:闲聊|我|随口|说|在聊))"
    r"|那只(?!是(?:我|随口|说|在聊))"
    r"|上一只|刚才那(?!边)|同上|这票|那票"
)
# 「别」只作否定动词；特别 / 分别 / 差别 / 别的 不算
_NEG_WORD = (
    r"(?:不要|不用|无需|不必|先别|(?<![特分差性别告鉴级个识区])别(?![的人墅克]))"
)

ROUTE_HEAVY = "heavy_research"
ROUTE_LIGHT = "light_research"
ROUTE_CHAT = "chat"


_NEG_EMAIL_RE = re.compile(
    rf"{_NEG_WORD}.{{0,8}}(?:发邮件|发信|发送|发到|邮件|邮箱|发)"
)


def _negated(text: str, keyword: str) -> bool:
    """关键词前有否定时，不把该词当成抬档或发信。"""
    return bool(
        re.search(rf"{_NEG_WORD}.{{0,6}}{re.escape(keyword)}", text or "")
    )


def _detect_want_email(text: str, *, has_email: bool) -> bool:
    """根据话术关键词或已提取邮箱判断用户是否要求发信。"""
    if _NEG_EMAIL_RE.search(text or ""):
        return False
    if has_email:
        return True
    low = (text or "").lower()
    return any(kw in text or kw in low for kw in _EMAIL_KEYWORDS)


def _route_for_known_symbol(text: str) -> str:
    """已有标的时分档：明确分析/研报/对比为重投研，其余为轻投研。发信本身不抬档。"""
    if _COMPARE_RE.search(text) and not _negated(text, "对比") and not _negated(text, "比较"):
        return ROUTE_HEAVY
    if re.search(r"分析(?!得)", text or "") and not _negated(text, "分析"):
        return ROUTE_HEAVY
    if _HEAVY_RE.search(text or ""):
        for keyword in (
            "研究报告",
            "深度分析",
            "近日行情",
            "走势分析",
            "生成报告",
            "写报告",
            "出报告",
            "研报",
        ):
            if keyword in text and not _negated(text, keyword):
                return ROUTE_HEAVY
        if re.search(r"深度(?!睡眠|学习|优先|思考)", text or "") and not _negated(
            text, "深度"
        ):
            return ROUTE_HEAVY
    return ROUTE_LIGHT


def _looks_like_continuation(text: str) -> bool:
    """话术是否在指代上一只（它 / 这只 / 上一只等）。"""
    return bool(_CONTINUE_RE.search(text or ""))


def _parse_intent_by_llm(user_input: str) -> dict[str, Any]:
    """LLM 兜底解析；失败抛异常。不信任裸代码，代码仍须代码表校验。"""
    raw = chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "你是股票投研意图解析器。只输出一个 JSON 对象，不要 markdown。"
                    "字段：asset_name(股票中文名或null)、asset_code(6位代码或null)、"
                    "want_email(bool)、to_email(邮箱或null)、"
                    "continues_previous(bool，本轮是否在指代上一只股票，如「它」「这只」)、"
                    "route(heavy_research|light_research|chat)。"
                    "明确要分析、研报、对比时 route=heavy_research；"
                    "只问现价、涨跌、怎么样等为 light_research；"
                    "闲聊或没有股票为 chat。"
                    "单独说发邮件不要因此填 heavy_research。"
                    "若无法识别股票，名称与代码皆 null。"
                ),
            },
            {"role": "user", "content": user_input},
        ]
    )
    matched = _JSON_BLOCK.search(raw)
    data = json.loads(matched.group(0) if matched else raw)
    asset_name = data.get("asset_name") or None
    asset_code = data.get("asset_code") or None
    to_email = data.get("to_email") or None
    if isinstance(asset_name, str):
        asset_name = asset_name.strip() or None
    if isinstance(asset_code, str):
        asset_code = asset_code.strip() or None
    if isinstance(to_email, str):
        to_email = to_email.strip() or None
    else:
        to_email = None
    route = data.get("route")
    if route not in (ROUTE_HEAVY, ROUTE_LIGHT, ROUTE_CHAT):
        route = None
    return {
        "asset_name": asset_name,
        "asset_code": asset_code,
        "want_email": bool(data.get("want_email")),
        "to_email": to_email,
        "continues_previous": bool(data.get("continues_previous")),
        "route": route,
    }


def _base_intent(user_input: str) -> dict[str, Any]:
    to_email = extract_email_from_text(user_input)
    return {
        "asset_name": None,
        "asset_code": None,
        "want_email": _detect_want_email(user_input, has_email=bool(to_email)),
        "to_email": to_email,
        "continues_previous": False,
        "compare_unsupported": False,
    }


def _pack(
    intent: dict[str, Any],
    route: str,
    errors: list[str],
    *,
    extra: dict | None = None,
) -> dict:
    """统一写出 route，并由 route 推导 skip_analysts。"""
    out = {
        "intent": intent,
        "route": route,
        "skip_analysts": route != ROUTE_HEAVY,
        "errors": errors,
    }
    if extra:
        out.update(extra)
    return out


def _remember(state: dict, intent: dict[str, Any]) -> None:
    """heavy / light 成功解析后写入标的槽；chat 不写。"""
    set_research_context(
        state.get("conversation_id"),
        code=intent.get("asset_code"),
        name=intent.get("asset_name"),
    )


def _apply_symbol(
    intent: dict[str, Any],
    symbol: dict,
    *,
    user_input: str,
    multi: bool,
) -> str:
    """写入标的；多标的或话术含对比时标记暂不支持对比，并返回 route。"""
    intent["asset_code"] = symbol["code"]
    intent["asset_name"] = symbol["name"]
    intent["compare_unsupported"] = bool(multi or _COMPARE_RE.search(user_input))
    return _route_for_known_symbol(user_input)


def _resolve_llm_symbol(user_input: str, parsed: dict[str, Any]) -> dict | None:
    """只接受代码表能对上的名称；话术里没出现的 LLM 代码一律丢弃。"""
    name = parsed.get("asset_name")
    if name:
        resolved = resolve_symbol(name=str(name), code=None)
        if resolved:
            return resolved
    code = parsed.get("asset_code")
    if code and str(code) in user_input:
        return resolve_symbol(name=None, code=str(code))
    return None


def coordinator_node(state: dict) -> dict:
    """一次判定 route、标的与是否沿用上一只；Redis 失败不抛业务错误。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        intent = dict(state.get("intent") or _base_intent(state.get("user_input") or ""))
        intent.setdefault("continues_previous", False)
        return {
            **patch,
            "intent": intent,
            "route": ROUTE_CHAT,
            "skip_analysts": True,
        }

    user_input = (state.get("user_input") or "").strip()
    intent = _base_intent(user_input)
    errors: list[str] = []

    symbols = extract_symbols_from_text(user_input)
    if symbols:
        route = _apply_symbol(
            intent,
            symbols[0],
            user_input=user_input,
            multi=len(symbols) > 1,
        )
        _remember(state, intent)
        return _pack(intent, route, errors)

    # 续指优先于「解析失败落 chat」：本轮无代码但话术在指代上一只
    if _looks_like_continuation(user_input):
        intent["continues_previous"] = True
        previous = get_research_context(state.get("conversation_id"))
        if previous:
            route = _apply_symbol(
                intent,
                previous,
                user_input=user_input,
                multi=False,
            )
            _remember(state, intent)
            return _pack(intent, route, errors)
        intent["clarify_previous"] = True
        return _pack(intent, ROUTE_CHAT, errors)

    parsed: dict[str, Any] = {}
    try:
        parsed = _parse_intent_by_llm(user_input)
    except Exception as exc:
        errors.append(f"coordinator_parse_failed: {exc}")
        parsed = {}

    if parsed:
        intent["want_email"] = intent["want_email"] or bool(parsed.get("want_email"))
        if not intent.get("to_email"):
            llm_email = extract_email_from_text(str(parsed.get("to_email") or ""))
            if llm_email:
                intent["to_email"] = llm_email
                intent["want_email"] = True

    continues = _looks_like_continuation(user_input) or bool(
        parsed.get("continues_previous")
    )
    intent["continues_previous"] = continues

    resolved = _resolve_llm_symbol(user_input, parsed) if parsed else None
    if resolved:
        route = _apply_symbol(
            intent, resolved, user_input=user_input, multi=False
        )
        _remember(state, intent)
        return _pack(intent, route, errors)

    mentioned = None
    if parsed:
        mentioned = parsed.get("asset_name") or parsed.get("asset_code")
    # 提到了标的但对不上代码表：闲聊说明不在覆盖范围，不写标的槽
    if mentioned and not continues:
        errors.append("symbol_resolve_failed")
        intent["uncovered_name"] = str(parsed.get("asset_name") or mentioned)
        return _pack(intent, ROUTE_CHAT, errors)

    # 规则没判续指、但 LLM 认为在指上一只时，再读一次标的槽
    if continues:
        previous = get_research_context(state.get("conversation_id"))
        if previous:
            route = _apply_symbol(
                intent,
                previous,
                user_input=user_input,
                multi=False,
            )
            _remember(state, intent)
            return _pack(intent, route, errors)
        intent["clarify_previous"] = True
        return _pack(intent, ROUTE_CHAT, errors)

    return _pack(intent, ROUTE_CHAT, errors)
