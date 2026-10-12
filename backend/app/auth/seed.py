import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User

SEED_PERMISSIONS: list[tuple[str, str]] = [
    ("doc:upload", "上传文档"),
    ("doc:list", "文档列表"),
    ("doc:delete", "删除文档"),
    ("chat:ask", "发起问答"),
    ("chat:history", "会话历史"),
]

SEED_ROLES: list[tuple[str, str]] = [
    ("admin", "管理员"),
    ("user", "普通用户"),
]

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123456"  # 仅本地演示；入库为 bcrypt


def _hash_password(plain: str) -> str:
    """种子专用 bcrypt（与 security 独立，避免启动耦合）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _get_or_create_role(db: Session, code: str, name: str) -> Role:
    """按 code 取角色，不存在则创建。"""
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=name)
        db.add(role)
        db.flush()
    return role


def _get_or_create_permission(db: Session, code: str, name: str) -> Permission:
    """按 code 取权限，不存在则创建。"""
    perm = db.scalar(select(Permission).where(Permission.code == code))
    if perm is None:
        perm = Permission(code=code, name=name, type="api")
        db.add(perm)
        db.flush()
    return perm


def _ensure_role_permission(db: Session, role_id: int, permission_id: int) -> None:
    """确保角色-权限关联存在。"""
    exists = db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    if exists is None:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))


def _ensure_user_role(db: Session, user_id: int, role_id: int) -> None:
    """确保用户-角色关联存在。"""
    exists = db.scalar(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )
    )
    if exists is None:
        db.add(UserRole(user_id=user_id, role_id=role_id))


def run_seed(db: Session) -> None:
    """幂等写入角色/权限/关联与默认 admin；已存在用户不改密码。"""
    roles = {
        code: _get_or_create_role(db, code, name) for code, name in SEED_ROLES
    }
    permissions = [
        _get_or_create_permission(db, code, name) for code, name in SEED_PERMISSIONS
    ]

    for role in roles.values():
        for perm in permissions:
            _ensure_role_permission(db, role.id, perm.id)

    admin_user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    if admin_user is None:
        admin_user = User(
            username=ADMIN_USERNAME,
            password_hash=_hash_password(ADMIN_PASSWORD),
            status="ACTIVE",
        )
        db.add(admin_user)
        db.flush()

    _ensure_user_role(db, admin_user.id, roles["admin"].id)
    db.commit()
