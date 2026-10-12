from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode


def chat_completion(messages: list[dict[str, str]]) -> str:
    """一次性非流式生成；返回 assistant 文本。"""
    settings = get_settings()
    if not settings.LLM_API_KEY:
        raise AppError(ErrorCode.LLM_FAILED, "未配置 LLM_API_KEY", http_status=500)

    llm = ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL.rstrip("/"),
        model=settings.LLM_MODEL,
        temperature=0.2,
        timeout=120.0,
        max_retries=1,
    )
    try:
        resp = llm.invoke(_to_lc_messages(messages))
        content = resp.content if isinstance(resp.content, str) else str(resp.content or "")
        return content.strip()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.LLM_FAILED, f"LLM 调用失败: {exc}", http_status=500
        ) from exc


def _to_lc_messages(messages: list[dict[str, str]]):
    """dict 消息 → LangChain Message 对象。"""
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out
