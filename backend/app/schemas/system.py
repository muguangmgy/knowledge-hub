from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """管理端新建用户。"""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    roleIds: list[int] = Field(default_factory=list)
    status: int = Field(default=1)  # 1=正常 / 0=禁用


class UserUpdateRequest(BaseModel):
    """管理端更新用户；字段均为可选，仅提交变更项。"""

    status: int | None = None
    roleIds: list[int] | None = None
    password: str | None = Field(default=None, min_length=1, max_length=128)


class RoleCreateRequest(BaseModel):
    """新建角色；menuIds 为方案 A 勾选（多为叶子）。"""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    menuIds: list[int] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    """更新角色名称与/或菜单绑定。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    menuIds: list[int] | None = None


class MenuCreateRequest(BaseModel):
    """新建菜单节点（catalog / menu / button）。"""

    parentId: int = 0
    name: str = Field(min_length=1, max_length=128)
    path: str | None = None
    icon: str | None = None
    type: str = Field(min_length=1, max_length=32)
    perms: str | None = None  # 本版仅存档，不用于接口拦截
    sort: int = 0
    visible: int = 1  # 1=显示 / 0=隐藏
    status: int = 1  # 1=正常 / 0=禁用


class MenuUpdateRequest(BaseModel):
    """更新菜单；字段均为可选。"""

    parentId: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    path: str | None = None
    icon: str | None = None
    type: str | None = None
    perms: str | None = None
    sort: int | None = None
    visible: int | None = None
    status: int | None = None
