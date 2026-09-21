from typing import Any

from ag_ui.core import RunAgentInput
from pydantic import BaseModel, ConfigDict, Field


class AgUiRunRequest(RunAgentInput):
    """DeepClaw 扩展的 AG-UI Run 输入。

    Args:
        agent_id: 顶层智能体 ID；为空时使用默认智能体。
    """

    agent_id: str | None = Field(default=None, description="智能体 ID")


class RunSnapshotResponse(BaseModel):
    """AG-UI Run 状态快照。"""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="runId")
    thread_id: str = Field(alias="threadId")
    agent_id: str = Field(default="agent", alias="agentId")
    status: str
    last_event_id: str | None = Field(default=None, alias="lastEventId")
    event_count: int = Field(default=0, alias="eventCount")
    created_at: float | None = Field(default=None, alias="createdAt")
    updated_at: float | None = Field(default=None, alias="updatedAt")
    error: str | None = None


class RunActionRequest(BaseModel):
    """AG-UI Action 恢复请求。"""

    decisions: list[dict[str, Any]] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class ThreadRunListResponse(BaseModel):
    """Thread 下的 Run 列表响应。"""

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    items: list[RunSnapshotResponse] = Field(default_factory=list)
    total: int = 0


class ThreadDeleteResponse(BaseModel):
    """Thread 删除响应。"""

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    deleted: bool


class ThreadSummaryResponse(BaseModel):
    """Thread 摘要。"""

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    agent_id: str = Field(default="agent", alias="agentId")
    title: str | None = None
    created_at: float = Field(alias="createdAt")
    updated_at: float = Field(alias="updatedAt")


class ThreadListResponse(BaseModel):
    """当前用户的 Thread 列表响应。"""

    items: list[ThreadSummaryResponse] = Field(default_factory=list)
    total: int = 0


class AgentSummaryResponse(BaseModel):
    """可用智能体摘要。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    is_default: bool = Field(default=False, alias="default")
    capabilities: list[str] = Field(default_factory=list)


class AgentListResponse(BaseModel):
    """可用智能体列表响应。"""

    items: list[AgentSummaryResponse] = Field(default_factory=list)
    total: int = 0
