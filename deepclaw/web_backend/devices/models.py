"""设备、配对与执行任务的持久化模型。"""

import time
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Device(SQLModel, table=True):
    """独立凭据绑定的用户设备，权限以客户端上报为准。"""

    __tablename__ = "devices"
    id: str = Field(primary_key=True)
    owner_user_id: str = Field(index=True)
    name: str
    platform: str
    token_hash: str = Field(unique=True, index=True)
    revoked: bool = False
    enabled: bool = False
    revision: int = 0
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    roots: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    connection_id: str | None = None
    last_seen: float = 0
    created_at: float = Field(default_factory=time.time)


class DevicePairing(SQLModel, table=True):
    """一次性、短时有效的设备配对码，仅存散列。"""

    __tablename__ = "device_pairings"
    code_hash: str = Field(primary_key=True)
    owner_user_id: str
    expires_at: float
    used: bool = False


class DeviceTask(SQLModel, table=True):
    """客户端工具执行记录，稳定 ID 用于重连去重。"""

    __tablename__ = "device_tasks"
    id: str = Field(primary_key=True)
    device_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    tool_call_id: str = Field(index=True)
    thread_id: str
    operation: str
    arguments: dict = Field(sa_column=Column(JSON, nullable=False))
    revision: int
    status: str = Field(default="pending", index=True)
    output: str = ""
    sequence: int = 0
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    cancel_requested: bool = False
    created_at: float = Field(default_factory=time.time)
    expires_at: float
