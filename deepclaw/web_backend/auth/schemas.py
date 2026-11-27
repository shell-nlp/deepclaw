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
        display_name: 可选显示名；留空时界面显示用户名。
        email: 可选邮箱。
    """

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: str = Field(default="user", min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
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
    role: str = Field(min_length=1, max_length=128)


class AdminUpdateUserStatusRequest(BaseModel):
    """管理员修改用户状态请求。

    Args:
        user_id: 目标用户 ID。
        is_active: 是否启用。
    """

    user_id: str
    is_active: bool


class AdminUpdateUserProfileRequest(BaseModel):
    """管理员修改用户资料请求。

    Args:
        user_id: 目标用户 ID。
        username: 新用户名；为空表示不修改。
        display_name: 新显示名；传空字符串表示清空。
        email: 新邮箱；传空字符串表示清空。
    """

    user_id: str
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=64)
    email: str | None = None


class AdminDeleteUserRequest(BaseModel):
    """管理员删除用户请求。

    Args:
        user_id: 目标用户 ID。
    """

    user_id: str


class AdminResetUserPasswordRequest(BaseModel):
    """管理员重置密码请求。

    Args:
        user_id: 目标用户 ID。
        password: 新密码。
    """

    user_id: str
    password: str = Field(min_length=8)
