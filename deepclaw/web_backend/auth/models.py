from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuthUser(SQLModel, table=True):
    """用户账号。

    Args:
        username: 登录用户名，唯一且必填。
        email: 可选邮箱，仅作附加资料展示，可为空且不要求唯一。
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    username: str | None = Field(default=None, index=True, unique=True)
    email: str | None = Field(default=None, index=True)
    password_hash: str
    role: str = Field(default="user")
    is_active: bool = True
    # 连续登录失败次数与临时锁定截止时间，用于暴力破解防护
    failed_login_attempts: int = Field(default=0)
    locked_until: datetime | None = Field(default=None, sa_type=DateTime)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)


class AccessTokenRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime = Field(sa_type=DateTime)
    last_used_at: datetime | None = Field(default=None, sa_type=DateTime)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)


@dataclass(slots=True)
class IssuedAccessToken:
    token: str
    user: AuthUser
    record: AccessTokenRecord


@dataclass(slots=True)
class AuthenticatedActor:
    user: AuthUser
    record: AccessTokenRecord
