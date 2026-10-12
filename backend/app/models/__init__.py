"""ORM 模型汇总：导入本包即可注册全部表，供 lifespan create_all。"""

from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User

__all__ = [
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "Document",
    "Chunk",
    "Conversation",
    "Message",
]
