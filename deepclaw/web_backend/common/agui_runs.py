from __future__ import annotations

from collections.abc import Callable
from typing import Any, Iterable

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from deepclaw.settings import settings
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor


_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


def get_agent_runs_path() -> str:
    """返回 Agent AG-UI Runs 路径。

    Returns:
        固定为 ``/api/agent/runs``。
    """
    return "/api/agent/runs"


def get_rag_runs_path() -> str:
    """返回 RAG AG-UI Runs 路径。

    Returns:
        固定为 ``/api/rag/runs``。
    """
    return "/api/rag/runs"


def get_channel_agent_api_url(
    *,
    explicit_url: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
) -> str:
    """解析渠道调用的 Agent Runs 完整 URL。

    Args:
        explicit_url: 可选完整覆盖 URL；非空时直接使用。
        host: 自动拼接时使用的主机名。
        port: 自动拼接时使用的端口；为空时取 settings.PORT。

    Returns:
        渠道可调用的 Agent Runs URL。
    """
    if explicit_url:
        return explicit_url
    resolved_port = settings.PORT if port is None else port
    return f"http://{host}:{resolved_port}{get_agent_runs_path()}"


def get_runtime_api_config() -> dict[str, str]:
    """构造前端 runtime-config 响应体。

    Returns:
        包含 Agent/RAG Runs 路径的配置字典。
    """
    return {
        "agent_runs_path": get_agent_runs_path(),
        "rag_runs_path": get_rag_runs_path(),
    }


runtime_router = APIRouter(tags=["runtime"])


@runtime_router.get(
    "/api/runtime-config",
    summary="获取前端运行时配置",
    description="返回前端需要使用的 Agent 与 RAG AG-UI Runs 路径。",
)
async def runtime_config() -> dict[str, str]:
    """返回前端运行时 AG-UI 路径配置。"""
    return get_runtime_api_config()


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


def _event_cursor(run_id: str, value: str | None) -> int:
    """解析 AG-UI Run 的 Last-Event-ID。

    Args:
        run_id: 当前 Run ID。
        value: `Last-Event-ID` 或查询参数中的游标。

    Returns:
        事件序号；格式不合法时返回 0。
    """
    if not value:
        return 0
    prefix = f"{run_id}:"
    raw = value[len(prefix) :] if value.startswith(prefix) else value
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _actor_user_id(actor: CurrentActor) -> str:
    """解析服务端可信用户 ID。

    Args:
        actor: 当前鉴权主体。

    Returns:
        登录用户 ID 或固定游客 ID。
    """
    if actor.is_guest or not actor.user_id:
        return "guest"
    return actor.user_id


def _trusted_state(
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor,
    allowed_keys: Iterable[str],
) -> dict[str, Any]:
    """构造 AG-UI 运行状态，覆盖客户端不可伪造的身份字段。

    Args:
        payload: 客户端提交的 AG-UI 输入。
        request: 当前 HTTP 请求，用于提取请求头。
        actor: 当前鉴权主体。
        allowed_keys: 允许从客户端 state 传入的运行参数。

    Returns:
        经过服务端信任边界处理后的 LangGraph state。
    """
    source = payload.state if isinstance(payload.state, dict) else {}
    state = {key: source[key] for key in allowed_keys if key in source}
    state["user_id"] = _actor_user_id(actor)
    state["header_info"] = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _SENSITIVE_HEADER_NAMES
    }
    return state


def _with_trusted_state(
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor,
    allowed_keys: Iterable[str],
) -> RunAgentInput:
    """返回带有可信服务端 state 的 AG-UI 输入副本。

    Args:
        payload: 原始 AG-UI 输入。
        request: 当前 HTTP 请求。
        actor: 当前鉴权主体。
        allowed_keys: 允许的客户端运行参数字段。

    Returns:
        更新后的 AG-UI 输入。
    """
    return payload.model_copy(update={"state": _trusted_state(payload, request, actor, allowed_keys)})


def create_agui_run_router(
    manager: AgentRunManager | Callable[..., AgentRunManager],
    *,
    allowed_state_keys: set[str],
    tags: list[str],
) -> APIRouter:
    """创建统一 AG-UI Run 生命周期路由。

    Args:
        manager: Run 管理器实例，或按请求解析管理器的依赖提供函数。
        allowed_state_keys: 客户端可设置的非身份 state 字段。
        tags: FastAPI OpenAPI 标签。

    Returns:
        包含 runs、events、snapshot、resume、actions、cancel 的路由器。
    """
    if callable(manager) and not isinstance(manager, AgentRunManager):
        manager_provider = manager
    else:
        manager_instance = manager

        def manager_provider() -> AgentRunManager:
            """返回固定 Run 管理器实例。

            Returns:
                当前路由器绑定的 Run 管理器。
            """
            return manager_instance

    router = APIRouter(tags=tags)
    encoder = EventEncoder()

    @router.post(
        "/runs",
        status_code=202,
        response_model=RunSnapshot,
        summary="创建 AG-UI Run",
        description="创建一次 Agent 或 RAG 运行并返回 Run Snapshot，后续通过事件接口订阅 AG-UI 事件流。",
    )
    async def create_run(
        payload: RunAgentInput,
        request: Request,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """创建 AG-UI Run 并异步执行。"""
        try:
            trusted_payload = _with_trusted_state(payload, request, actor, allowed_state_keys)
            return await resolved_manager.create(trusted_payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get(
        "/runs/{run_id}",
        response_model=RunSnapshot,
        summary="获取 AG-UI Run",
        description="查询指定 Run 的当前状态、事件游标、更新时间和错误信息。",
    )
    async def get_run(
        run_id: str,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """读取 AG-UI Run Snapshot。"""
        snapshot = await resolved_manager.get_snapshot(run_id, user_id=_actor_user_id(actor))
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Run 不存在")
        return snapshot

    @router.get(
        "/runs/{run_id}/events",
        summary="订阅 AG-UI Run 事件",
        description="以 SSE 流式返回 AG-UI 事件，支持通过 Last-Event-ID 从指定位置重放。",
    )
    async def run_events(
        run_id: str,
        request: Request,
        after: str | None = None,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """以 AG-UI SSE 事件流重放或续流指定 Run。"""
        user_id = _actor_user_id(actor)
        snapshot = await resolved_manager.get_snapshot(run_id, user_id=user_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Run 不存在")
        cursor = _event_cursor(run_id, request.headers.get("last-event-id") or after)
        return StreamingResponse(
            resolved_manager.events(run_id, after=cursor, user_id=user_id),
            media_type=encoder.get_content_type(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post(
        "/runs/{run_id}/resume",
        status_code=202,
        response_model=RunSnapshot,
        summary="恢复 AG-UI Run",
        description="提交表单、审批或中断恢复输入，继续执行同一个 Run。",
    )
    async def resume_run(
        run_id: str,
        payload: RunAgentInput,
        request: Request,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """提交 AG-UI command.resume，恢复同一线程的中断运行。"""
        try:
            trusted_payload = _with_trusted_state(payload, request, actor, allowed_state_keys)
            return await resolved_manager.continue_run(
                run_id,
                trusted_payload,
                user_id=_actor_user_id(actor),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/runs/{run_id}/actions",
        status_code=202,
        response_model=RunSnapshot,
        summary="处理 AG-UI Action",
        description="将前端卡片 Action 转换为 AG-UI resume 命令并继续当前 Run。",
    )
    async def handle_action(
        run_id: str,
        payload: RunActionRequest,
        request: Request,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """将卡片 Action 转换为 AG-UI command.resume。"""
        user_id = _actor_user_id(actor)
        previous = await resolved_manager.get_input(run_id, user_id=user_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="Run 不存在")
        forwarded_props = dict(previous.forwarded_props or {})
        forwarded_props["command"] = {"resume": {"decisions": payload.decisions}}
        next_payload = previous.model_copy(
            update={
                "run_id": run_id,
                "forwarded_props": forwarded_props,
            }
        )
        next_payload = _with_trusted_state(next_payload, request, actor, allowed_state_keys)
        try:
            return await resolved_manager.continue_run(run_id, next_payload, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/runs/{run_id}/cancel",
        response_model=RunSnapshot,
        summary="取消 AG-UI Run",
        description="请求取消指定 Run，并返回取消后的 Run Snapshot。",
    )
    async def cancel_run(
        run_id: str,
        actor: CurrentActor = Depends(get_current_actor),
        resolved_manager: AgentRunManager = Depends(manager_provider),
    ):
        """取消 AG-UI Run。"""
        snapshot = await resolved_manager.cancel(run_id, user_id=_actor_user_id(actor))
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Run 不存在")
        return snapshot

    return router
