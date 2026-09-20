from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request

from deepclaw.agents.rag.agent import create_rag_agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import get_run_store
from deepclaw.web_backend.common.agui_runs import create_agui_run_router


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
router.include_router(
    create_agui_run_router(
        get_rag_run_manager,
        allowed_state_keys={
            "index_name",
            "graph_name",
            "internet_search",
            "deep_thinking",
        },
        tags=["rag-ag-ui"],
    )
)


def create_rag_router() -> APIRouter:
    """返回模块级 RAG 路由器。"""
    return router
