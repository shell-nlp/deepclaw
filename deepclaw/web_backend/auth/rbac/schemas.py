from pydantic import BaseModel, Field


class RbacCatalogPermissionResponse(BaseModel):
    """角色拥有的直接策略权限。

    Args:
        path: Casbin 路径匹配表达式。
        action: 动作名称。
    """

    path: str
    action: str


class RbacCatalogRoleResponse(BaseModel):
    """角色目录视图。

    Args:
        id: 稳定角色标识。
        name: 角色名称。
        description: 角色说明。
        builtin: 是否内置。
        user_count: 使用角色的账号数量。
        permissions: 角色直接拥有的权限。
    """

    id: str
    name: str
    description: str
    builtin: bool
    user_count: int
    permissions: list[RbacCatalogPermissionResponse]


class RbacCatalogListResponse(BaseModel):
    """角色目录列表。

    Args:
        roles: 全部角色视图。
    """

    roles: list[RbacCatalogRoleResponse]


class RbacCatalogCreateRequest(BaseModel):
    """新增目录角色请求。

    Args:
        id: 不可变角色标识。
        name: 角色名称。
        description: 角色说明。
    """

    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)


class RbacCatalogUpdateRequest(BaseModel):
    """修改角色名称与说明请求。

    Args:
        name: 可选角色名称。
        description: 可选说明。
    """

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)


class RbacCatalogPermissionRequest(BaseModel):
    """单项策略替换请求。

    Args:
        path: Casbin 路径规则。
        action: 权限动作。
    """

    path: str = Field(min_length=1, max_length=512)
    action: str = Field(min_length=1, max_length=32)


class RbacCatalogPermissionsRequest(BaseModel):
    """批量替换角色权限请求。

    Args:
        permissions: 新的全部直接权限。
    """

    permissions: list[RbacCatalogPermissionRequest]


class RbacPolicyItemResponse(BaseModel):
    """单条策略响应。

    Args:
        subject: 策略主体。
        path: 资源路径。
        action: 动作名称。
    """

    subject: str
    path: str
    action: str


class RbacRoleItemResponse(BaseModel):
    """单条角色继承响应。

    Args:
        child: 子角色或被授予角色的用户 ID。
        parent: 父角色。
    """

    child: str
    parent: str


class RbacPolicyListResponse(BaseModel):
    """策略与角色完整视图。

    Args:
        policies: 策略列表。
        roles: 角色继承列表。
    """

    policies: list[RbacPolicyItemResponse]
    roles: list[RbacRoleItemResponse]


class RbacPolicyCreateRequest(BaseModel):
    """新增策略请求。

    Args:
        subject: 策略主体，角色名或用户 ID。
        path: 资源路径，按 keyMatch 规则匹配。
        action: 动作名称，例如 read 或 write。
    """

    subject: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=512)
    action: str = Field(min_length=1, max_length=32)


class RbacPolicyDeleteRequest(BaseModel):
    """删除策略请求。

    Args:
        subject: 策略主体。
        path: 资源路径。
        action: 动作名称。
    """

    subject: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=512)
    action: str = Field(min_length=1, max_length=32)


class RbacRoleCreateRequest(BaseModel):
    """新增角色继承请求。

    Args:
        child: 子角色或被授予角色的用户 ID。
        parent: 父角色。
    """

    child: str = Field(min_length=1, max_length=128)
    parent: str = Field(min_length=1, max_length=128)


class RbacRoleDeleteRequest(BaseModel):
    """删除角色继承请求。

    Args:
        child: 子角色或被授予角色的用户 ID。
        parent: 父角色。
    """

    child: str = Field(min_length=1, max_length=128)
    parent: str = Field(min_length=1, max_length=128)
