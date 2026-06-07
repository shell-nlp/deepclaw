from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuthUser(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    role: str = Field(default="user")
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AccessTokenRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    last_used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


@dataclass(slots=True)
class IssuedAccessToken:
    token: str
    user: AuthUser
    record: AccessTokenRecord


@dataclass(slots=True)
class AuthenticatedActor:
    user: AuthUser
    record: AccessTokenRecord
