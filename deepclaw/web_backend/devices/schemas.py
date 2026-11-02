"""设备管理 HTTP 与连接协议模型。"""

from typing import Literal
from pydantic import BaseModel, Field


class PairingResponse(BaseModel):
    """仅创建时返回的配对码。"""

    code: str
    expires_at: float


class PairingClaimRequest(BaseModel):
    """客户端使用配对码领取独立凭据。"""

    code: str = Field(min_length=16, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    platform: str = Field(min_length=1, max_length=40)


class PairingClaimResponse(BaseModel):
    """设备凭据只在领取时返回一次。"""

    device_id: str
    token: str


class DeviceResponse(BaseModel):
    """当前用户可见的设备，包含明确的连接与授权状态。"""

    id: str
    name: str
    platform: str
    online: bool
    enabled: bool
    revision: int
    capabilities: list[str]
    roots: list[str]
    last_seen: float


class DeviceListResponse(BaseModel):
    """用户设备列表。"""

    items: list[DeviceResponse]


class DeviceTaskResponse(BaseModel):
    """任务进度及输出。"""

    id: str
    device_id: str
    operation: str
    arguments: dict
    status: str
    output: str
    result: dict | None
    cancel_requested: bool
    created_at: float


class DeviceTaskListResponse(BaseModel):
    """最近设备任务。"""

    items: list[DeviceTaskResponse]


class DevicePolicyRequest(BaseModel):
    """只能由持有设备凭据的客户端更新的授权。"""

    type: Literal["policy"] = "policy"
    enabled: bool
    revision: int = Field(ge=1)
    capabilities: list[Literal["files.read", "files.write", "command.run"]] = Field(max_length=3)
    roots: list[str] = Field(max_length=32)


class DeviceEventRequest(BaseModel):
    """带单调序号的任务状态与输出。"""

    type: Literal["task_event"] = "task_event"
    task_id: str
    sequence: int = Field(ge=1)
    status: Literal["queued", "awaiting_approval", "running", "succeeded", "failed", "cancelled", "rejected", "uncertain"]
    output: str = Field(default="", max_length=16384)
    result: dict | None = None
