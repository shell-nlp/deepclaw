from __future__ import annotations

import asyncio
from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends, Query, Request

from deepclaw.agents.rag.agent import create_rag_agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import get_run_store
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


_rag_graph_cache: dict[tuple[int, int, int], Any] = {}
_rag_run_manager_cache: dict[tuple[int, int, int], AgentRunManager] = {}


def get_checkpointer(request: Request) -> Any | None:
    """从应用状态读取 RAG 检查点存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的检查点存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "checkpointer", None)


def get_rag_store(request: Request) -> Any | None:
    """从应用状态读取 RAG 长期存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的长期存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "store", None)


async def get_rag_graph(
    request: Request,
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_rag_store),
) -> Any:
    """按应用状态懒加载并缓存 RAG 图。

    Args:
        request: 当前 FastAPI 请求。
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        当前应用使用的 RAG 图。
    """
    cache_key = (id(request.app), id(checkpointer), id(store))
    cached = _rag_graph_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "rag_graph_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.rag_graph_lock = lock

    async with lock:
        cached = _rag_graph_cache.get(cache_key)
        if cached is None:
            cached = create_rag_agent(checkpointer, store)
            _rag_graph_cache[cache_key] = cached
    return cached


async def get_rag_run_manager(
    request: Request,
    graph: Any = Depends(get_rag_graph),
) -> AgentRunManager:
    """按 RAG 图懒加载并缓存 AG-UI Run 管理器。

    Args:
        request: 当前 FastAPI 请求。
        graph: 当前应用的 RAG 图。

    Returns:
        当前应用使用的 Run 管理器。
    """
    run_store = get_run_store()
    cache_key = (id(request.app), id(graph), id(run_store))
    cached = _rag_run_manager_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "rag_run_manager_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.rag_run_manager_lock = lock

    async with lock:
        cached = _rag_run_manager_cache.get(cache_key)
        if cached is None:
            cached = AgentRunManager(graph, store=run_store)
            _rag_run_manager_cache[cache_key] = cached
    return cached


router = APIRouter(prefix="/api/rag")
_RAG_ALLOWED_STATE_KEYS = {
    "index_name",
    "graph_name",
    "internet_search",
    "deep_thinking",
}


@router.post(
    "/runs",
    status_code=202,
    response_model=RunSnapshot,
    tags=["rag-ag-ui"],
    summary="创建 RAG AG-UI Run",
    description="创建一次 RAG 运行并返回 Run Snapshot，后续通过事件接口订阅 AG-UI 事件流。",
)
async def create_rag_run(
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """创建 RAG AG-UI Run。"""
    return await create_agui_run(manager, payload, request, actor, _RAG_ALLOWED_STATE_KEYS)


@router.get(
    "/runs/{run_id}",
    response_model=RunSnapshot,
    tags=["rag-ag-ui"],
    summary="获取 RAG AG-UI Run",
    description="查询指定 RAG Run 的当前状态、事件游标、更新时间和错误信息。",
)
async def get_rag_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """读取 RAG AG-UI Run Snapshot。"""
    return await get_agui_run_snapshot(manager, run_id, actor)


@router.get(
    "/runs/{run_id}/events",
    tags=["rag-ag-ui"],
    summary="订阅 RAG AG-UI Run 事件",
    description="以 SSE 流式返回 RAG AG-UI 事件，支持通过 Last-Event-ID 从指定位置重放。",
)
async def rag_run_events(
    run_id: str,
    request: Request,
    after: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """订阅 RAG AG-UI Run 事件。"""
    return await stream_agui_run_events(manager, run_id, request, after, actor)


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=RunSnapshot,
    tags=["rag-ag-ui"],
    summary="恢复 RAG AG-UI Run",
    description="提交表单、审批或中断恢复输入，继续执行同一个 RAG Run。",
)
async def resume_rag_run(
    run_id: str,
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """恢复 RAG AG-UI Run。"""
    return await resume_agui_run(
        manager,
        run_id,
        payload,
        request,
        actor,
        _RAG_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/actions",
    status_code=202,
    response_model=RunSnapshot,
    tags=["rag-ag-ui"],
    summary="处理 RAG AG-UI Action",
    description="将前端卡片 Action 转换为 AG-UI resume 命令并继续当前 RAG Run。",
)
async def handle_rag_action(
    run_id: str,
    payload: RunActionRequest,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """处理 RAG AG-UI Action。"""
    return await handle_agui_action(
        manager,
        run_id,
        payload,
        request,
        actor,
        _RAG_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunSnapshot,
    tags=["rag-ag-ui"],
    summary="取消 RAG AG-UI Run",
    description="请求取消指定 RAG Run，并返回取消后的 Run Snapshot。",
)
async def cancel_rag_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """取消 RAG AG-UI Run。"""
    return await cancel_agui_run(manager, run_id, actor)


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    tags=["rag-thread"],
    summary="查询 Thread 列表",
    description="返回当前用户可见的 Thread 列表。",
)
async def list_threads(
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """查询当前用户的 Thread 列表。"""
    return await list_agui_threads(manager, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/runs",
    response_model=ThreadRunListResponse,
    tags=["rag-thread"],
    summary="查询 RAG Thread 下的 Run",
    description="返回指定 Thread 下属于当前用户的 RAG Run 列表。",
)
async def list_rag_thread_runs(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
):
    """查询 RAG Thread 下的 Run。"""
    return await list_agui_thread_runs(manager, thread_id, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/state",
    tags=["rag-thread"],
    summary="查询 RAG Thread 状态",
    description="返回指定 Thread 的 LangGraph state。",
)
async def get_rag_thread_state(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
    graph: Any = Depends(get_rag_graph),
):
    """查询 RAG Thread 状态。"""
    return await get_agui_thread_state(manager, graph, thread_id, actor)


@router.delete(
    "/threads/{thread_id}",
    response_model=ThreadDeleteResponse,
    tags=["rag-thread"],
    summary="删除 RAG Thread",
    description="删除指定 Thread 的 checkpoint、Run 和事件记录。",
)
async def delete_rag_thread(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_rag_run_manager),
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """删除 RAG Thread。"""
    return await delete_agui_thread(manager, checkpointer, thread_id, actor)


