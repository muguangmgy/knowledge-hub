import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.audit import actor_scope
from app.models.rbac import Menu, Role, RoleMenu, UserRole
from app.models.user import User

SEED_ROLES: list[tuple[str, str]] = [
    ("admin", "管理员"),
    ("user", "普通用户"),
]

# key, parent_key, sort, name, type, path, perms, bind_admin, bind_user
# 业务三项为根级平铺（无「业务功能」目录）；系统管理仍为 catalog + 子菜单
SEED_MENUS: list[tuple[str, str | None, int, str, str, str | None, str | None, bool, bool]] = [
    ("sys", None, 10, "系统管理", "catalog", None, "system:catalog", False, False),
    ("sys_users", "sys", 11, "用户管理", "menu", "/system/users", "system:user:list", True, False),
    ("sys_roles", "sys", 12, "角色管理", "menu", "/system/roles", "system:role:list", True, False),
    ("sys_menus", "sys", 13, "菜单管理", "menu", "/system/menus", "system:menu:list", True, False),
    ("sys_dev", "sys", 14, "开发调试", "menu", "/system/dev", "system:dev:debug", True, False),
    ("biz_rag", None, 20, "知识库问答", "menu", "/chat/rag", "biz:chat:rag", True, True),
    ("biz_direct", None, 21, "投研助手", "menu", "/chat/direct", "biz:chat:direct", True, True),
    ("biz_docs", None, 22, "文档", "menu", "/documents", "biz:doc:list", True, True),
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


def _find_menu(db: Session, *, path: str | None, perms: str | None) -> Menu | None:
    """按 path（菜单）或 perms（目录）定位已有种子节点。"""
    if path:
        return db.scalar(select(Menu).where(Menu.path == path))
    if perms:
        return db.scalar(
            select(Menu).where(Menu.perms == perms, Menu.type == "catalog")
        )
    return None


def _get_or_create_menu(
    db: Session,
    *,
    parent_id: int,
    sort: int,
    name: str,
    type_: str,
    path: str | None,
    perms: str | None,
) -> Menu:
    """幂等创建菜单节点；已存在则同步 parent_id / sort / name / type / perms。"""
    existing = _find_menu(db, path=path, perms=perms)
    if existing is not None:
        existing.parent_id = parent_id
        existing.sort = sort
        existing.name = name
        existing.type = type_
        existing.perms = perms
        if path is not None:
            existing.path = path
        return existing
    menu = Menu(
        parent_id=parent_id,
        name=name,
        path=path,
        icon=None,
        type=type_,
        perms=perms,
        sort=sort,
        visible=1,
        status=1,
    )
    db.add(menu)
    db.flush()
    return menu


def _remove_obsolete_biz_catalog(db: Session) -> None:
    """删除旧版「业务功能」目录（perms=biz:catalog）及 role_menu。"""
    obsolete = db.scalar(
        select(Menu).where(Menu.perms == "biz:catalog", Menu.type == "catalog")
    )
    if obsolete is None:
        return
    db.execute(delete(RoleMenu).where(RoleMenu.menu_id == obsolete.id))
    db.delete(obsolete)
    db.flush()


def _ensure_role_menu(db: Session, role_id: int, menu_id: int) -> None:
    """确保角色-菜单关联存在。"""
    exists = db.scalar(
        select(RoleMenu).where(
            RoleMenu.role_id == role_id,
            RoleMenu.menu_id == menu_id,
        )
    )
    if exists is None:
        db.add(RoleMenu(role_id=role_id, menu_id=menu_id))


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


def _stamp_actor(row, actor_id: int) -> None:
    """历史行若尚无审计人，回写为 actor。"""
    if getattr(row, "created_by", None) is None:
        row.created_by = actor_id
    if getattr(row, "updated_by", None) is None:
        row.updated_by = actor_id


def run_seed(db: Session) -> None:
    """幂等写入角色/菜单/关联与默认 admin；已存在用户不改密码。"""
    roles = {code: _get_or_create_role(db, code, name) for code, name in SEED_ROLES}

    admin_user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    if admin_user is None:
        admin_user = User(
            username=ADMIN_USERNAME,
            password_hash=_hash_password(ADMIN_PASSWORD),
            status=1,
        )
        db.add(admin_user)
        db.flush()

    actor_id = admin_user.id
    with actor_scope(actor_id):
        _stamp_actor(admin_user, actor_id)
        for role in roles.values():
            _stamp_actor(role, actor_id)

        # 先去掉旧「业务功能」目录，再写入平铺业务菜单
        _remove_obsolete_biz_catalog(db)

        key_to_menu: dict[str, Menu] = {}
        for (
            key,
            parent_key,
            sort,
            name,
            type_,
            path,
            perms,
            bind_admin,
            bind_user,
        ) in SEED_MENUS:
            parent_id = 0
            if parent_key is not None:
                parent_id = key_to_menu[parent_key].id
            menu = _get_or_create_menu(
                db,
                parent_id=parent_id,
                sort=sort,
                name=name,
                type_=type_,
                path=path,
                perms=perms,
            )
            _stamp_actor(menu, actor_id)
            key_to_menu[key] = menu
            if bind_admin:
                _ensure_role_menu(db, roles["admin"].id, menu.id)
            if bind_user:
                _ensure_role_menu(db, roles["user"].id, menu.id)

        _ensure_user_role(db, admin_user.id, roles["admin"].id)

        for row in db.scalars(select(UserRole)).all():
            _stamp_actor(row, actor_id)
        for row in db.scalars(select(RoleMenu)).all():
            _stamp_actor(row, actor_id)

        db.commit()
