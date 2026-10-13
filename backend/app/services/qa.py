from __future__ import annotations

from app.llm.client import chat_completion
from app.rag.retriever import RetrievedChunk

# 规则拒答固定话术（rejected=true，业务仍 code=0）
REJECT_REPLY = "依据不足，无法基于知识库回答该问题。"


def build_citations(chunks: list[RetrievedChunk], *, titles: dict[int, str]) -> list[dict]:
    """按检索顺序生成短摘录引用列表，index 从 1 起。"""
    citations: list[dict] = []
    for i, c in enumerate(chunks, start=1):
        snippet = c.content.strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:200] + "…"
        citations.append(
            {
                "index": i,
                "doc_id": c.document_id,
                "chunk_id": c.chunk_id,
                "title": titles.get(c.document_id) or c.filename or str(c.document_id),
                "heading_path": c.heading_path,
                "snippet": snippet,
            }
        )
    return citations


def generate_answer(
    *,
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]],
    titles: dict[int, str],
) -> str:
    """拼 system + 可选最近历史 + 当前问题与片段；要求答案用 [n] 标注。"""
    context_parts: list[str] = []
    for i, c in enumerate(chunks, start=1):
        title = titles.get(c.document_id) or c.filename
        context_parts.append(
            f"[{i}] 文档={title} | 小节={c.heading_path or '正文'}\n{c.content}"
        )
    context = "\n\n".join(context_parts)

    system = (
        "你是企业知识库助手。只能依据给定检索片段回答问题，并在相关句子后用 [n] 标注来源编号。"
        "只根据已给出的片段作答：片段有多少信息就答多少，不要编造缺失内容；"
        "也不要输出「原文未完整」「内容缺失」「依据不足」等元说明"
        "（整题确实无法回答时除外，此时直接说无法基于知识库回答）。"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append(
        {
            "role": "user",
            "content": f"检索片段：\n{context}\n\n用户问题：{question}",
        }
    )
    return chat_completion(messages)
