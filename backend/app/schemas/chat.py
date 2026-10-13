from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """问答请求；conversationId 缺省则懒建会话。"""

    message: str = Field(min_length=1)
    conversationId: int | None = None
