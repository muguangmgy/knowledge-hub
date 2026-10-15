from __future__ import annotations

from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.common.config import get_settings
from app.common.errors import AppError, ErrorCode


def _build_llm(*, streaming: bool = False) -> ChatOpenAI:
    """按 Settings 构造 ChatOpenAI；streaming 控制是否走上游 SSE。"""
    settings = get_settings()
    if not settings.LLM_API_KEY:
        raise AppError(ErrorCode.LLM_FAILED, "未配置 LLM_API_KEY", http_status=500)
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL.rstrip("/"),
        model=settings.LLM_MODEL,
        temperature=0.2,
        timeout=120.0,
        max_retries=1,
        streaming=streaming,
    )


def chat_completion(messages: list[dict[str, str]]) -> str:
    """一次性非流式生成；返回 assistant 文本。"""
    llm = _build_llm(streaming=False)
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


def chat_completion_stream(messages: list[dict[str, str]]) -> Iterator[str]:
    """流式生成；逐段 yield 文本增量（可能为空串，调用方可跳过）。"""
    llm = _build_llm(streaming=True)
    try:
        for chunk in llm.stream(_to_lc_messages(messages)):
            content = chunk.content if hasattr(chunk, "content") else ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # 部分模型返回 content blocks
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
                    elif hasattr(block, "text"):
                        parts.append(str(getattr(block, "text") or ""))
                text = "".join(parts)
            else:
                text = str(content or "")
            if text:
                yield text
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
