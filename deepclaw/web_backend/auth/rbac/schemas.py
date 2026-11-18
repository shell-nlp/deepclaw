from pydantic import BaseModel, Field


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
