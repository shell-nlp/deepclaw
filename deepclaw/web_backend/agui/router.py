from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from deepclaw.agent_registry import AgentRegistry
from deepclaw.web_backend.agent.run_store import (
    RunStore,
    get_or_backfill_thread,
    get_run_store,
)
from deepclaw.web_backend.agui.runtime import AgentRuntimeCache
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_runs import (
    _actor_user_id,
    cancel_agui_run_from_store,
    create_agui_run,
    delete_agui_thread,
    get_agui_run_snapshot_from_store,
    get_agui_thread_state,
    list_agui_thread_runs,
    list_agui_threads,
    resume_agui_run,
    stream_agui_run_events_from_store,
)
from deepclaw.web_backend.common.agui_schemas import (
    AgentListResponse,
    AgentSummaryResponse,
    AgUiRunRequest,
    RunSnapshotResponse,
    ThreadDeleteResponse,
    ThreadListResponse,
    ThreadRunListResponse,
)

def get_agent_runtime_cache(request: Request) -> AgentRuntimeCache:
    """返回当前应用的智能体运行时缓存。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用使用的智能体运行时缓存。
    """
    return request.app.state.agent_runtime_cache


def get_checkpointer(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 检查点存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的检查点存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "checkpointer", None)


def get_langgraph_store(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 长期存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的长期存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "store", None)


def get_agui_run_store() -> RunStore:
    """返回进程级 AG-UI Run 存储。

    Args:
        无。

    Returns:
        当前进程共享的 Run/Thread 存储。
    """
    return get_run_store()


async def _resolve_run_manager(
    *,
    request: Request,
    run_id: str,
    actor: CurrentActor,
    run_store: RunStore,
    registry: AgentRegistry,
    runtime_registry: AgentRuntimeCache,
    checkpointer: Any | None,
    store: Any | None,
):
    """按 Run 持久化的 agent_id 解析执行管理器。

    Args:
        request: 当前 FastAPI 请求。
        run_id: Run ID。
        actor: 当前鉴权主体。
        run_store: AG-UI Run 存储。
        registry: 智能体注册表。
        runtime_registry: 智能体运行时注册表。
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        Run 对应的状态与执行管理器。

    Raises:
        HTTPException: Run 不存在或未知智能体时返回错误。
    """
    state = await run_store.get_run(run_id, user_id=_actor_user_id(actor))
    if state is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    try:
        agent = registry.get(state.agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    graph = await runtime_registry.get_graph(
        request.app,
        agent,
        checkpointer,
        store,
    )
    manager = await runtime_registry.get_manager(
        request.app,
        agent,
        graph,
        run_store,
    )
    return state, agent, manager


router = APIRouter(prefix="/api/agui")


@router.get(
    "/agents",
    response_model=AgentListResponse,
    tags=["agui-agents"],
    summary="查询可用智能体",
    description="返回当前服务可调用的智能体列表。",
)
async def list_agents(
    request: Request,
) -> AgentListResponse:
    """查询可用智能体列表。"""
    registry = request.app.state.agent_registry
    items = [
        AgentSummaryResponse(
            id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            is_default=agent.is_default,
            capabilities=list(agent.capabilities),
        )
        for agent in registry.list_agents()
    ]
    return AgentListResponse(items=items, total=len(items))


@router.post(
    "/runs",
    status_code=202,
    response_model=RunSnapshotResponse,
    tags=["agui-runs"],
    summary="创建 AG-UI Run",
    description="通过顶层 agentId 选择智能体，并创建一次 AG-UI 运行。",
)
async def create_run(
    payload: AgUiRunRequest,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    runtime_registry: AgentRuntimeCache = Depends(get_agent_runtime_cache),
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_langgraph_store),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """创建统一 AG-UI Run。"""
    registry = request.app.state.agent_registry
    try:
        agent = registry.resolve(payload.agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    graph = await runtime_registry.get_graph(
        request.app,
        agent,
        checkpointer,
        store,
    )
    manager = await runtime_registry.get_manager(
        request.app,
        agent,
        graph,
        run_store,
    )
    return await create_agui_run(
        manager,
        payload,
        request,
        actor,
        agent.allowed_state_keys,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunSnapshotResponse,
    tags=["agui-runs"],
    summary="获取 AG-UI Run",
    description="查询指定 Run 的当前状态、事件游标、更新时间和错误信息。",
)
async def get_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """读取统一 AG-UI Run Snapshot。"""
    return await get_agui_run_snapshot_from_store(run_store, run_id, actor)


@router.get(
    "/runs/{run_id}/events",
    tags=["agui-runs"],
    summary="订阅 AG-UI Run 事件",
    description="以 SSE 流式返回 AG-UI 事件，支持通过 Last-Event-ID 重放。",
)
async def run_events(
    run_id: str,
    request: Request,
    after: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """订阅统一 AG-UI Run 事件。"""
    return await stream_agui_run_events_from_store(
        run_store,
        run_id,
        request,
        after,
        actor,
    )


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=RunSnapshotResponse,
    tags=["agui-runs"],
    summary="恢复 AG-UI Run",
    description="提交表单、审批或中断恢复输入，继续执行同一个 Run。",
)
async def resume_run(
    run_id: str,
    payload: AgUiRunRequest,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    runtime_registry: AgentRuntimeCache = Depends(get_agent_runtime_cache),
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_langgraph_store),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """恢复统一 AG-UI Run。"""
    registry = request.app.state.agent_registry
    state, agent, manager = await _resolve_run_manager(
        request=request,
        run_id=run_id,
        actor=actor,
        run_store=run_store,
        registry=registry,
        runtime_registry=runtime_registry,
        checkpointer=checkpointer,
        store=store,
    )
    if payload.agent_id and payload.agent_id != state.agent_id:
        raise HTTPException(status_code=409, detail="agentId 与当前 Run 不一致")
    return await resume_agui_run(
        manager,
        run_id,
        payload,
        request,
        actor,
        agent.allowed_state_keys,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunSnapshotResponse,
    tags=["agui-runs"],
    summary="取消 AG-UI Run",
    description="请求取消指定 Run，并返回取消后的 Run Snapshot。",
)
async def cancel_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """取消统一 AG-UI Run。"""
    return await cancel_agui_run_from_store(run_store, run_id, actor)


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    tags=["agui-threads"],
    summary="查询 Thread 列表",
    description="返回当前用户可见的 Thread 列表，可按 agentId 过滤。",
)
async def list_threads(
    agent_id: str | None = Query(default=None, alias="agentId"),
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """查询当前用户的 Thread 列表。"""
    return await list_agui_threads(
        run_store,
        actor,
        agent_id=agent_id,
        limit=limit,
    )


@router.get(
    "/threads/{thread_id}/runs",
    response_model=ThreadRunListResponse,
    tags=["agui-threads"],
    summary="查询 Thread 下的 Run",
    description="返回指定 Thread 下属于当前用户的 Run 列表。",
)
async def list_thread_runs(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """查询指定 Thread 下的 Run。"""
    return await list_agui_thread_runs(
        run_store,
        thread_id,
        actor,
        limit=limit,
    )


@router.get(
    "/threads/{thread_id}/state",
    tags=["agui-threads"],
    summary="查询 Thread 状态",
    description="返回指定 Thread 的 LangGraph state。",
)
async def get_thread_state(
    thread_id: str,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    runtime_registry: AgentRuntimeCache = Depends(get_agent_runtime_cache),
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_langgraph_store),
    run_store: RunStore = Depends(get_agui_run_store),
):
    """查询指定 Thread 的图状态。"""
    registry = request.app.state.agent_registry
    thread = await get_or_backfill_thread(
        run_store,
        thread_id,
        user_id=_actor_user_id(actor),
    )
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread 不存在")
    try:
        agent = registry.get(thread.agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    graph = await runtime_registry.get_graph(
        request.app,
        agent,
        checkpointer,
        store,
    )
    return await get_agui_thread_state(
        run_store,
        graph,
        thread_id,
        actor,
    )


@router.delete(
    "/threads/{thread_id}",
    response_model=ThreadDeleteResponse,
    tags=["agui-threads"],
    summary="删除 Thread",
    description="删除指定 Thread 的 checkpoint、Run 和事件记录。",
)
async def delete_thread(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    run_store: RunStore = Depends(get_agui_run_store),
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """删除指定 Thread。"""
    return await delete_agui_thread(
        run_store,
        checkpointer,
        thread_id,
        actor,
    )
