from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """问答请求；conversationId 缺省则懒建会话。"""

    message: str = Field(min_length=1, description="用户问题")
    conversationId: int | None = Field(
        default=None, description="已有会话 ID；缺省则懒建"
    )
    mode: str | None = Field(
        default=None,
        description="对话模式 rag | direct；缺省或 null 按 rag（见 chat.normalize_chat_mode）",
    )


class ConversationUpdateRequest(BaseModel):
    """更新会话标题。"""

    title: str = Field(min_length=1, max_length=512)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("标题不能为空")
        return cleaned
