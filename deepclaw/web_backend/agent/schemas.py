from pydantic import BaseModel, Field


class GetHistoryRequest(BaseModel):
    """Agent 会话状态查询请求。"""

    session_id: str


class DeleteSessionRequest(BaseModel):
    """Agent 会话删除请求。"""

    session_id: str


class SessionSummary(BaseModel):
    """Agent 会话摘要。"""

    session_id: str
    updated_at: str | None = None
    title: str | None = None


class SessionListResponse(BaseModel):
    """Agent 会话列表响应。"""

    sessions: list[SessionSummary] = Field(default_factory=list)
    total: int = 0


class DeleteSessionResponse(BaseModel):
    """删除 Agent 会话响应。"""

    session_id: str
