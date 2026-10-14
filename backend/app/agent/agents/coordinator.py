from __future__ import annotations

import json
import re
from typing import Any

from app.agent.logging_util import check_deadline
from app.agent.tools.email import extract_email_from_text
from app.agent.tools.symbol import extract_symbol_from_text, resolve_symbol
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


def _detect_want_email(text: str, *, has_email: bool) -> bool:
    """根据话术关键词或已提取邮箱判断用户是否要求发信。"""
    if has_email:
        return True
    low = (text or "").lower()
    return any(kw in text or kw in low for kw in _EMAIL_KEYWORDS)


def _parse_intent_by_llm(user_input: str) -> dict[str, Any]:
    """LLM 兜底解析；失败抛异常。"""
    raw = chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "你是股票投研意图解析器。只输出一个 JSON 对象，不要 markdown。"
                    '字段：asset_name(股票中文名或null)、asset_code(6位代码或null)、'
                    "want_email(bool，用户是否要求发到邮箱)、"
                    "to_email(用户点名的邮箱字符串或null，未写具体地址则为null)。"
                    "分析窗口固定为近30个自然日，无需输出。若无法识别股票，名称与代码皆 null。"
                ),
            },
            {"role": "user", "content": user_input},
        ]
    )
    m = _JSON_BLOCK.search(raw)
    data = json.loads(m.group(0) if m else raw)
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
    return {
        "asset_name": asset_name,
        "asset_code": asset_code,
        "want_email": bool(data.get("want_email")),
        "to_email": to_email,
    }


def coordinator_node(state: dict) -> dict:
    """解析标的与发信意图；规则优先，失败再 LLM 兜底并校验代码表。"""
    patch = check_deadline(state)
    if patch.get("timed_out"):
        return {
            **patch,
            "skip_analysts": True,
            "intent": state.get("intent") or {},
        }

    user_input = (state.get("user_input") or "").strip()
    to_email = extract_email_from_text(user_input)
    want_email = _detect_want_email(user_input, has_email=bool(to_email))
    intent: dict[str, Any] = {
        "asset_name": None,
        "asset_code": None,
        "want_email": want_email,
        "to_email": to_email,
    }
    errors: list[str] = []

    # Step 1: 规则优先（代码 / 证券简称 + 发信关键词 / 邮箱）
    ruled = extract_symbol_from_text(user_input)
    if ruled:
        intent["asset_code"] = ruled["code"]
        intent["asset_name"] = ruled["name"]
        return {
            "intent": intent,
            "skip_analysts": False,
            "errors": errors,
        }

    # Step 2: 规则未命中 → LLM 兜底
    try:
        parsed = _parse_intent_by_llm(user_input)
        intent["asset_name"] = parsed.get("asset_name")
        intent["asset_code"] = parsed.get("asset_code")
        intent["want_email"] = want_email or bool(parsed.get("want_email"))
        if not intent.get("to_email"):
            llm_email = extract_email_from_text(str(parsed.get("to_email") or ""))
            if llm_email:
                intent["to_email"] = llm_email
                intent["want_email"] = True
    except Exception as exc:
        errors.append(f"coordinator_parse_failed: {exc}")
        return {
            "intent": intent,
            "skip_analysts": True,
            "errors": errors,
        }

    if not intent.get("asset_name") and not intent.get("asset_code"):
        return {
            "intent": intent,
            "skip_analysts": True,
            "errors": errors,
        }

    resolved = resolve_symbol(
        name=intent.get("asset_name"),
        code=intent.get("asset_code"),
    )
    if not resolved:
        errors.append("symbol_resolve_failed")
        return {
            "intent": intent,
            "skip_analysts": True,
            "errors": errors,
        }

    intent["asset_code"] = resolved["code"]
    intent["asset_name"] = resolved["name"]
    return {
        "intent": intent,
        "skip_analysts": False,
        "errors": errors,
    }
