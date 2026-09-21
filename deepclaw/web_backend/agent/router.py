from __future__ import annotations

import asyncio
from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends, Query, Request
from deepclaw.agents.general.agent import Agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import RunStore, get_run_store
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_runs import (
    cancel_agui_run,
    create_agui_run,
    delete_agui_thread,
    get_agui_run_snapshot,
    get_agui_thread_state,
    handle_agui_action,
    list_agui_thread_runs,
    list_agui_threads,
    resume_agui_run,
    stream_agui_run_events,
)
from deepclaw.web_backend.common.agui_schemas import (
    RunActionRequest,
    RunSnapshot,
    ThreadDeleteResponse,
    ThreadListResponse,
    ThreadRunListResponse,
)


_agent_graph_cache: dict[tuple[int, int, int], Any] = {}
_agent_run_manager_cache: dict[tuple[int, int, int], AgentRunManager] = {}


def get_checkpointer(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 检查点存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的检查点存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "checkpointer", None)


def get_agent_store(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 长期存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的长期存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "store", None)


def get_agent_run_store() -> RunStore:
    """返回进程级 Run/Thread 存储。

    Args:
        无。

    Returns:
        当前进程共享的 Run/Thread 存储。
    """
    return get_run_store()


async def get_agent_graph(
    request: Request,
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_agent_store),
) -> Any:
    """按应用状态懒加载并缓存 Agent 图。

    Args:
        request: 当前 FastAPI 请求。
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        当前应用使用的 Agent 图。
    """
    cache_key = (id(request.app), id(checkpointer), id(store))
    cached = _agent_graph_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "agent_graph_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.agent_graph_lock = lock

    async with lock:
        cached = _agent_graph_cache.get(cache_key)
        if cached is None:
            cached = Agent(
                deep_agent=True,
                checkpointer=checkpointer,
                store=store,
            ).get_agent()
            _agent_graph_cache[cache_key] = cached
    return cached


async def get_agent_run_manager(
    request: Request,
    graph: Any = Depends(get_agent_graph),
) -> AgentRunManager:
    """按 Agent 图懒加载并缓存 AG-UI Run 管理器。

    Args:
        request: 当前 FastAPI 请求。
        graph: 当前应用的 Agent 图。

    Returns:
        当前应用使用的 Run 管理器。
    """
    run_store = get_run_store()
    cache_key = (id(request.app), id(graph), id(run_store))
    cached = _agent_run_manager_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "agent_run_manager_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.agent_run_manager_lock = lock

    async with lock:
        cached = _agent_run_manager_cache.get(cache_key)
        if cached is None:
            cached = AgentRunManager(graph, store=run_store)
            _agent_run_manager_cache[cache_key] = cached
    return cached


router = APIRouter(prefix="/api/agent")
_AGENT_ALLOWED_STATE_KEYS = {"internet_search", "deep_thinking", "mcp_config"}


@router.post(
    "/runs",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="创建 Agent AG-UI Run",
    description="创建一次 Agent 运行并返回 Run Snapshot，后续通过事件接口订阅 AG-UI 事件流。",
)
async def create_agent_run(
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """创建 Agent AG-UI Run。"""
    return await create_agui_run(manager, payload, request, actor, _AGENT_ALLOWED_STATE_KEYS)


@router.get(
    "/runs/{run_id}",
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="获取 Agent AG-UI Run",
    description="查询指定 Agent Run 的当前状态、事件游标、更新时间和错误信息。",
)
async def get_agent_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """读取 Agent AG-UI Run Snapshot。"""
    return await get_agui_run_snapshot(manager, run_id, actor)


@router.get(
    "/runs/{run_id}/events",
    tags=["agent-ag-ui"],
    summary="订阅 Agent AG-UI Run 事件",
    description="以 SSE 流式返回 Agent AG-UI 事件，支持通过 Last-Event-ID 从指定位置重放。",
)
async def agent_run_events(
    run_id: str,
    request: Request,
    after: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """订阅 Agent AG-UI Run 事件。"""
    return await stream_agui_run_events(manager, run_id, request, after, actor)


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="恢复 Agent AG-UI Run",
    description="提交表单、审批或中断恢复输入，继续执行同一个 Agent Run。",
)
async def resume_agent_run(
    run_id: str,
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """恢复 Agent AG-UI Run。"""
    return await resume_agui_run(
        manager,
        run_id,
        payload,
        request,
        actor,
        _AGENT_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/actions",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="处理 Agent AG-UI Action",
    description="将前端卡片 Action 转换为 AG-UI resume 命令并继续当前 Agent Run。",
)
async def handle_agent_action(
    run_id: str,
    payload: RunActionRequest,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """处理 Agent AG-UI Action。"""
    return await handle_agui_action(
        manager,
        run_id,
        payload,
        request,
        actor,
        _AGENT_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="取消 Agent AG-UI Run",
    description="请求取消指定 Agent Run，并返回取消后的 Run Snapshot。",
)
async def cancel_agent_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """取消 Agent AG-UI Run。"""
    return await cancel_agui_run(manager, run_id, actor)


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    tags=["agent-thread"],
    summary="查询 Thread 列表",
    description="返回当前用户可见的 Thread 列表。",
)
async def list_threads(
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    store: RunStore = Depends(get_agent_run_store),
):
    """查询当前用户的 Thread 列表。"""
    return await list_agui_threads(store, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/runs",
    response_model=ThreadRunListResponse,
    tags=["agent-thread"],
    summary="查询 Agent Thread 下的 Run",
    description="返回指定 Thread 下属于当前用户的 Run 列表。",
)
async def list_agent_thread_runs(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    store: RunStore = Depends(get_agent_run_store),
):
    """查询 Agent Thread 下的 Run。"""
    return await list_agui_thread_runs(store, thread_id, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/state",
    tags=["agent-thread"],
    summary="查询 Agent Thread 状态",
    description="返回指定 Thread 的 LangGraph state。",
)
async def get_agent_thread_state(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    store: RunStore = Depends(get_agent_run_store),
    graph: Any = Depends(get_agent_graph),
):
    """查询 Agent Thread 状态。"""
    return await get_agui_thread_state(store, graph, thread_id, actor)


@router.delete(
    "/threads/{thread_id}",
    response_model=ThreadDeleteResponse,
    tags=["agent-thread"],
    summary="删除 Agent Thread",
    description="删除指定 Thread 的 checkpoint、Run 和事件记录。",
)
async def delete_agent_thread(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    store: RunStore = Depends(get_agent_run_store),
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """删除 Agent Thread。"""
    return await delete_agui_thread(store, checkpointer, thread_id, actor)
