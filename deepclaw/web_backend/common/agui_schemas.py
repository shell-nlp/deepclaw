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
