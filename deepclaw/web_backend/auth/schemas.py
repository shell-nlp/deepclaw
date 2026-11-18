from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """注册请求。

    Args:
        username: 登录用户名。
        password: 登录密码。
        email: 可选邮箱，仅作资料展示。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    email: str | None = None


class LoginRequest(BaseModel):
    """登录请求。

    Args:
        username: 登录用户名。
        password: 登录密码。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)


class AdminCreateUserRequest(BaseModel):
    """管理员创建用户请求。

    Args:
        username: 登录用户名。
        password: 初始密码。
        role: 用户角色。
        email: 可选邮箱。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: Literal["admin", "user"] = "user"
    email: str | None = None


class AdminListUsersRequest(BaseModel):
    """管理员查询用户请求。

    Args:
        search: 按用户名或邮箱模糊搜索。
    """

    search: str = ""


class AdminUpdateUserRoleRequest(BaseModel):
    """管理员修改角色请求。

    Args:
        user_id: 目标用户 ID。
        role: 新角色。
    """

    user_id: str
    role: Literal["admin", "user"]


class AdminUpdateUserStatusRequest(BaseModel):
    """管理员修改用户状态请求。

    Args:
        user_id: 目标用户 ID。
        is_active: 是否启用。
    """

    user_id: str
    is_active: bool


class AdminResetUserPasswordRequest(BaseModel):
    """管理员重置密码请求。

    Args:
        user_id: 目标用户 ID。
        password: 新密码。
    """

    user_id: str
    password: str = Field(min_length=8)
