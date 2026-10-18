"""文档批量接口请求体。"""

from pydantic import BaseModel, Field


class BatchDeleteRequest(BaseModel):
    """批量删除：文档 id 列表（业务校验在 service）。"""

    ids: list[int] = Field(description="要删除的文档 ID")
