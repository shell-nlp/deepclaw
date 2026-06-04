from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


ReplyMode = Literal["final", "streaming"]
AgentEventType = Literal["token", "tool_calls", "tool_output", "__interrupt__"]
MessageStatus = Literal["received", "processing", "done", "failed"]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ChannelUser(SQLModel, table=True):
    __tablename__ = "channel_users"
    __table_args__ = (
        UniqueConstraint("channel", "channel_user_id", name="uq_channel_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    user_id: str = Field(index=True)
    display_name: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelSession(SQLModel, table=True):
    __tablename__ = "channel_sessions"
    __table_args__ = (
        UniqueConstraint(
            "channel",
            "channel_conversation_id",
            "channel_user_id",
            name="uq_channel_session",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    channel_conversation_id: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    user_id: str = Field(index=True)
    session_id: str = Field(index=True, unique=True)
    reply_mode: str = Field(default="final")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelMessageRecord(SQLModel, table=True):
    __tablename__ = "channel_message_records"
    __table_args__ = (
        UniqueConstraint("channel", "message_id", name="uq_channel_message"),
    )

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    message_id: str = Field(index=True)
    channel_conversation_id: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    status: str = Field(default="received")
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelRuntimeState(SQLModel, table=True):
    __tablename__ = "channel_runtime_states"
    __table_args__ = (
        UniqueConstraint("channel", "state_key", name="uq_channel_runtime_state"),
    )

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    state_key: str = Field(default="default", index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ChannelMessage(BaseModel):
    channel: str
    message_id: str
    channel_user_id: str
    channel_conversation_id: str
    text: str
    message_type: str = "text"
    raw: dict[str, Any] | None = None


class AgentEvent(BaseModel):
    event: AgentEventType = "token"
    data: dict[str, Any] | None = None


class ChannelSessionUpdate(BaseModel):
    reply_mode: ReplyMode | None = None


class ChannelSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    channel_conversation_id: str
    channel_user_id: str
    user_id: str
    session_id: str
    reply_mode: str
    created_at: datetime
    updated_at: datetime


class ChannelSessionList(BaseModel):
    items: list[ChannelSessionRead] = PydanticField(default_factory=list)
    total: int = 0
