from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class AdminCreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: Literal["admin", "user"] = "user"


class AdminListUsersRequest(BaseModel):
    search: str = ""


class AdminUpdateUserRoleRequest(BaseModel):
    user_id: str
    role: Literal["admin", "user"]


class AdminUpdateUserStatusRequest(BaseModel):
    user_id: str
    is_active: bool


class AdminResetUserPasswordRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=8)

