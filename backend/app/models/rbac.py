from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class Role(Base):
    """角色（如 admin / user）。"""

    __tablename__ = "sys_role"
    __table_args__ = {"comment": "角色表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="角色ID"
    )
    code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="角色编码（如 admin / user）"
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="角色显示名称"
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id；种子可空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id；种子可空）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class Permission(Base):
    """权限码（本版仅供 /me 展示）。"""

    __tablename__ = "sys_permission"
    __table_args__ = {"comment": "权限表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="权限ID"
    )
    code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="权限编码（如 doc:upload、chat:ask）",
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="权限显示名称"
    )
    type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="api",
        comment="权限类型（本版种子均为 api）",
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id；种子可空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id；种子可空）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class UserRole(Base):
    """用户-角色关联。"""

    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        {"comment": "用户-角色关联表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="关联ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="用户ID（sys_user.id）"
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="角色ID（sys_role.id）"
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id；种子可空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id；种子可空）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class RolePermission(Base):
    """角色-权限关联。"""

    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        {"comment": "角色-权限关联表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="关联ID"
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="角色ID（sys_role.id）"
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="权限ID（sys_permission.id）"
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="创建人用户ID（sys_user.id；种子可空）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="修改人用户ID（sys_user.id；种子可空）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
