from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, UniqueConstraint, func
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


class Menu(Base):
    """菜单 / 目录 / 按钮。"""

    __tablename__ = "sys_menu"
    __table_args__ = {"comment": "菜单表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="菜单ID"
    )
    parent_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="父菜单ID；0=根"
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="显示名称"
    )
    path: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="前端路由 path"
    )
    icon: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="图标名"
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="catalog | menu | button"
    )
    perms: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="权限标识（本版不用于接口拦截）"
    )
    sort: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="同级排序升序"
    )
    visible: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="是否可见：1=显示，0=隐藏",
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default="1",
        comment="状态：1=正常，0=禁用",
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


class RoleMenu(Base):
    """角色-菜单关联（方案 A：只存勾选节点）。"""

    __tablename__ = "sys_role_menu"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_id", name="uq_role_menu"),
        {"comment": "角色-菜单关联表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="关联ID"
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="角色ID（sys_role.id）"
    )
    menu_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="菜单ID（sys_menu.id）"
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
