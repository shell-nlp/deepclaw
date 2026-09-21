from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request

from deepclaw.agent_registry import Agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import RunStore


class AgentRuntimeCache:
    """按应用和智能体缓存图与 Run 管理器。"""

    def __init__(self) -> None:
        """初始化运行时注册表。

        Args:
            无。
        """
        self._graphs: dict[tuple[int, str, int, int], Any] = {}
        self._managers: dict[tuple[int, str, int, int], AgentRunManager] = {}
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    def _lock_for(self, app_id: int, agent_id: str) -> asyncio.Lock:
        """获取指定应用和智能体的运行时锁。

        Args:
            app_id: FastAPI 应用 ID。
            agent_id: 智能体 ID。

        Returns:
            对应运行时锁。
        """
        key = (app_id, agent_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_graph(
        self,
        request: Request,
        definition: type[Agent],
        checkpointer: Any | None,
        store: Any | None,
    ) -> Any:
        """懒加载并缓存指定智能体的图。

        Args:
            request: 当前 FastAPI 请求。
            definition: 智能体定义。
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。

        Returns:
            已装配的 LangGraph 图。
        """
        app_id = id(request.app)
        cache_key = (
            app_id,
            definition.agent_id,
            id(checkpointer),
            id(store),
        )
        cached = self._graphs.get(cache_key)
        if cached is not None:
            return cached

        async with self._lock_for(app_id, definition.agent_id):
            cached = self._graphs.get(cache_key)
            if cached is None:
                cached = definition.build_agent(
                    checkpointer=checkpointer,
                    store=store,
                )
                self._graphs[cache_key] = cached
        return cached

    async def get_manager(
        self,
        request: Request,
        definition: type[Agent],
        graph: Any,
        run_store: RunStore,
    ) -> AgentRunManager:
        """懒加载并缓存指定智能体的 Run 管理器。

        Args:
            request: 当前 FastAPI 请求。
            definition: 智能体定义。
            graph: 已装配的 LangGraph 图。
            run_store: AG-UI Run 存储。

        Returns:
            指定智能体的 Run 管理器。
        """
        app_id = id(request.app)
        cache_key = (
            app_id,
            definition.agent_id,
            id(graph),
            id(run_store),
        )
        cached = self._managers.get(cache_key)
        if cached is not None:
            return cached

        async with self._lock_for(app_id, definition.agent_id):
            cached = self._managers.get(cache_key)
            if cached is None:
                cached = AgentRunManager(
                    graph,
                    store=run_store,
                    agent_id=definition.agent_id,
                )
                self._managers[cache_key] = cached
        return cached
