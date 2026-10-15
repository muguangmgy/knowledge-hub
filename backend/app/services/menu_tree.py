from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac import Menu, RoleMenu, UserRole

# 内置系统管理三页（不可删）
BUILTIN_MENU_PATHS = frozenset({"/system/users", "/system/roles", "/system/menus"})
# 内置「系统管理」目录（靠 perms 识别，无 path）
BUILTIN_CATALOG_PERMS = frozenset({"system:catalog"})


def is_builtin_menu(menu: Menu) -> bool:
    """内置系统管理目录及三菜单（不可删除）。"""
    if menu.path and menu.path in BUILTIN_MENU_PATHS:
        return True
    if menu.type == "catalog" and menu.perms in BUILTIN_CATALOG_PERMS:
        return True
    return False


def menu_to_node(menu: Menu, *, children: list | None = None) -> dict:
    """菜单 ORM → API camelCase 节点。"""
    return {
        "id": menu.id,
        "parentId": menu.parent_id,
        "name": menu.name,
        "path": menu.path,
        "icon": menu.icon,
        "type": menu.type,
        "perms": menu.perms,
        "sort": menu.sort,
        "visible": menu.visible,
        "status": menu.status,
        "children": children if children is not None else [],
    }


def build_menu_tree(menus: list[Menu]) -> list[dict]:
    """扁平菜单列表 → 树（按 parent_id + sort）。"""
    by_parent: dict[int, list[Menu]] = {}
    for m in menus:
        by_parent.setdefault(m.parent_id, []).append(m)
    for lst in by_parent.values():
        lst.sort(key=lambda x: (x.sort, x.id))

    def walk(parent_id: int) -> list[dict]:
        nodes = []
        for m in by_parent.get(parent_id, []):
            nodes.append(menu_to_node(m, children=walk(m.id)))
        return nodes

    return walk(0)


def load_all_menus(db: Session) -> list[Menu]:
    """全量菜单（管理端树）。"""
    return list(db.scalars(select(Menu).order_by(Menu.sort, Menu.id)).all())


def authorized_menu_ids_for_user(db: Session, user_id: int) -> set[int]:
    """用户角色下 role_menu 的 menu_id 去重（方案 A：库内多为叶子）。"""
    rows = db.execute(
        select(RoleMenu.menu_id)
        .join(UserRole, UserRole.role_id == RoleMenu.role_id)
        .where(UserRole.user_id == user_id)
    ).all()
    return {row[0] for row in rows}


def expand_menu_closure(db: Session, menu_ids: set[int]) -> list[Menu]:
    """
    授权闭包：纳入已授权节点及其祖先；
    仅保留 status=1 + visible=1 + catalog/menu。
    """
    if not menu_ids:
        return []

    all_menus = {m.id: m for m in load_all_menus(db)}
    included: set[int] = set()

    def include_with_ancestors(mid: int) -> None:
        cur = mid
        while cur and cur not in included:
            menu = all_menus.get(cur)
            if menu is None:
                break
            if (
                menu.status == 1
                and menu.visible == 1
                and menu.type in ("catalog", "menu")
            ):
                included.add(cur)
            parent = menu.parent_id
            if not parent:
                break
            cur = parent

    for mid in menu_ids:
        menu = all_menus.get(mid)
        if menu is None:
            continue
        if (
            menu.status != 1
            or menu.visible != 1
            or menu.type not in ("catalog", "menu")
        ):
            continue
        include_with_ancestors(mid)

    return [all_menus[i] for i in included if i in all_menus]


def menus_for_user(db: Session, user_id: int) -> list[dict]:
    """用户侧栏菜单树（含闭包）。"""
    ids = authorized_menu_ids_for_user(db, user_id)
    menus = expand_menu_closure(db, ids)
    return build_menu_tree(menus)
