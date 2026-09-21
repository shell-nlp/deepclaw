from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunSnapshot(BaseModel):
    """AG-UI Run 状态快照。"""

    runId: str
    threadId: str
    status: str
    lastEventId: str | None = None
    eventCount: int = 0
    createdAt: float | None = None
    updatedAt: float | None = None
    error: str | None = None


class RunActionRequest(BaseModel):
    """AG-UI Action 恢复请求。"""

    decisions: list[dict[str, Any]] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class ThreadRunListResponse(BaseModel):
    """Thread 下的 Run 列表响应。"""

    threadId: str
    items: list[RunSnapshot] = Field(default_factory=list)
    total: int = 0


class ThreadDeleteResponse(BaseModel):
    """Thread 删除响应。"""

    threadId: str
    deleted: bool


class ThreadSummary(BaseModel):
    """Thread 摘要。"""

    threadId: str
    title: str | None = None
    createdAt: float
    updatedAt: float


class ThreadListResponse(BaseModel):
    """当前用户的 Thread 列表响应。"""

    items: list[ThreadSummary] = Field(default_factory=list)
    total: int = 0
