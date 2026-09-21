from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from deepclaw.settings import settings
from deepclaw.web_backend.agent.run_manager import (
    AgentRunManager,
    ThreadOwnershipError,
    run_state_to_snapshot,
)
from deepclaw.web_backend.agent.run_store import RunStore, get_or_backfill_thread
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.common.agui_schemas import (
    RunActionRequest,
    ThreadDeleteResponse,
    ThreadListResponse,
    ThreadRunListResponse,
    ThreadSummary,
)


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


async def list_agui_threads(
    store: RunStore,
    actor: CurrentActor,
    *,
    limit: int,
) -> ThreadListResponse:
    """查询当前用户的 Thread 列表。

    Args:
        store: 当前域使用的 Run/Thread 存储。
        actor: 当前鉴权主体。
        limit: 最大返回数量。

    Returns:
        当前用户的 Thread 列表。
    """
    threads = await store.list_threads(
        _actor_user_id(actor),
        limit=limit,
    )
    items = [
        ThreadSummary(
            threadId=thread.thread_id,
            title=thread.title,
            createdAt=thread.created_at,
            updatedAt=thread.updated_at,
        )
        for thread in threads
    ]
    return ThreadListResponse(items=items, total=len(items))


async def list_agui_thread_runs(
    store: RunStore,
    thread_id: str,
    actor: CurrentActor,
    *,
    limit: int,
) -> ThreadRunListResponse:
    """查询指定 Thread 下的 Run。

    Args:
        store: 当前域使用的 Run/Thread 存储。
        thread_id: Thread ID。
        actor: 当前鉴权主体。
        limit: 最大返回数量。

    Returns:
        Thread 下的 Run 列表。

    Raises:
        HTTPException: Thread 不存在或无权访问时返回 404。
    """
    user_id = _actor_user_id(actor)
    thread = await get_or_backfill_thread(
        store,
        thread_id,
        user_id=user_id,
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread 不存在")
    runs = await store.list_runs_by_thread(
        thread_id,
        user_id=user_id,
        limit=limit,
    )
    items = [run_state_to_snapshot(run) for run in runs]
    return ThreadRunListResponse(threadId=thread_id, items=items, total=len(items))


async def get_agui_thread_state(
    store: RunStore,
    graph: Any,
    thread_id: str,
    actor: CurrentActor,
) -> dict[str, Any]:
    """读取指定 Thread 的图状态。

    Args:
        store: 当前域使用的 Run/Thread 存储。
        graph: 当前域使用的 LangGraph 图。
        thread_id: Thread ID。
        actor: 当前鉴权主体。

    Returns:
        Thread 的完整图状态。

    Raises:
        HTTPException: Thread 或状态不存在时返回 404。
    """
    thread = await get_or_backfill_thread(
        store,
        thread_id,
        user_id=_actor_user_id(actor),
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread 不存在")

    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await graph.aget_state(config)
    final_state = deepcopy(state_snapshot.values)
    messages = final_state.get("messages")
    if not messages:
        raise HTTPException(status_code=404, detail="Thread 状态不存在")
    title = getattr(messages[0], "content", None)
    if isinstance(title, str):
        final_state["title"] = title
    return final_state


async def delete_agui_thread(
    store: RunStore,
    checkpointer: Any | None,
    thread_id: str,
    actor: CurrentActor,
) -> ThreadDeleteResponse:
    """删除 Thread 的 checkpoint、Run 和事件记录。

    Args:
        store: 当前域使用的 Run/Thread 存储。
        checkpointer: LangGraph 检查点存储。
        thread_id: Thread ID。
        actor: 当前鉴权主体。

    Returns:
        Thread 删除结果。

    Raises:
        HTTPException: Thread 不存在、无权访问或删除失败时返回错误。
    """
    user_id = _actor_user_id(actor)
    thread = await get_or_backfill_thread(store, thread_id, user_id=user_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread 不存在")

    if checkpointer is not None:
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="删除 Thread 状态失败") from exc

    deleted = await store.delete_thread(thread_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread 不存在")
    return ThreadDeleteResponse(threadId=thread_id, deleted=True)


async def create_agui_run(
    manager: AgentRunManager,
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor,
    allowed_state_keys: Iterable[str],
) -> dict[str, Any]:
    """创建 AG-UI Run。

    Args:
        manager: 当前域使用的 Run 管理器。
        payload: 客户端提交的 AG-UI 输入。
        request: 当前 HTTP 请求。
        actor: 当前鉴权主体。
        allowed_state_keys: 允许从客户端 state 传入的字段。

    Returns:
        Run Snapshot。

    Raises:
        HTTPException: Run ID 冲突时返回 409。
    """
    try:
        trusted_payload = _with_trusted_state(payload, request, actor, allowed_state_keys)
        return await manager.create(trusted_payload)
    except ThreadOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def get_agui_run_snapshot(
    manager: AgentRunManager,
    run_id: str,
    actor: CurrentActor,
) -> dict[str, Any]:
    """读取 AG-UI Run Snapshot。

    Args:
        manager: 当前域使用的 Run 管理器。
        run_id: Run ID。
        actor: 当前鉴权主体。

    Returns:
        Run Snapshot。

    Raises:
        HTTPException: Run 不存在时返回 404。
    """
    snapshot = await manager.get_snapshot(run_id, user_id=_actor_user_id(actor))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return snapshot


async def stream_agui_run_events(
    manager: AgentRunManager,
    run_id: str,
    request: Request,
    after: str | None,
    actor: CurrentActor,
) -> StreamingResponse:
    """构建 AG-UI Run 的 SSE 事件流。

    Args:
        manager: 当前域使用的 Run 管理器。
        run_id: Run ID。
        request: 当前 HTTP 请求。
        after: 查询参数中的事件游标。
        actor: 当前鉴权主体。

    Returns:
        SSE StreamingResponse。
    """
    user_id = _actor_user_id(actor)
    snapshot = await manager.get_snapshot(run_id, user_id=user_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    cursor = _event_cursor(run_id, request.headers.get("last-event-id") or after)
    return StreamingResponse(
        manager.events(run_id, after=cursor, user_id=user_id),
        media_type=EventEncoder().get_content_type(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def resume_agui_run(
    manager: AgentRunManager,
    run_id: str,
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor,
    allowed_state_keys: Iterable[str],
) -> dict[str, Any]:
    """恢复 AG-UI Run。

    Args:
        manager: 当前域使用的 Run 管理器。
        run_id: Run ID。
        payload: 客户端提交的 AG-UI 输入。
        request: 当前 HTTP 请求。
        actor: 当前鉴权主体。
        allowed_state_keys: 允许从客户端 state 传入的字段。

    Returns:
        Run Snapshot。
    """
    try:
        trusted_payload = _with_trusted_state(payload, request, actor, allowed_state_keys)
        return await manager.continue_run(
            run_id,
            trusted_payload,
            user_id=_actor_user_id(actor),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def handle_agui_action(
    manager: AgentRunManager,
    run_id: str,
    payload: RunActionRequest,
    request: Request,
    actor: CurrentActor,
    allowed_state_keys: Iterable[str],
) -> dict[str, Any]:
    """处理 AG-UI 卡片 Action。

    Args:
        manager: 当前域使用的 Run 管理器。
        run_id: Run ID。
        payload: Action 恢复请求。
        request: 当前 HTTP 请求。
        actor: 当前鉴权主体。
        allowed_state_keys: 允许从客户端 state 传入的字段。

    Returns:
        Run Snapshot。
    """
    user_id = _actor_user_id(actor)
    previous = await manager.get_input(run_id, user_id=user_id)
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
        return await manager.continue_run(run_id, next_payload, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def cancel_agui_run(
    manager: AgentRunManager,
    run_id: str,
    actor: CurrentActor,
) -> dict[str, Any]:
    """取消 AG-UI Run。

    Args:
        manager: 当前域使用的 Run 管理器。
        run_id: Run ID。
        actor: 当前鉴权主体。

    Returns:
        取消后的 Run Snapshot。
    """
    snapshot = await manager.cancel(run_id, user_id=_actor_user_id(actor))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return snapshot
