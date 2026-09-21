from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from fastapi import Request

from deepclaw.agents.general.agent import Agent
from deepclaw.agents.rag.agent import create_rag_agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import RunStore


GraphFactory = Callable[[Any | None, Any | None], Any]


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """统一 AG-UI 路由可用的智能体定义。"""

    agent_id: str
    name: str
    description: str
    allowed_state_keys: frozenset[str]
    graph_factory: GraphFactory
    capabilities: tuple[str, ...] = ()
    is_default: bool = False


class AgentRegistry:
    """保存可用智能体定义并按 ID 解析。"""

    def __init__(self, specs: Iterable[AgentSpec]) -> None:
        """初始化智能体注册表。

        Args:
            specs: 可用智能体定义。
        """
        self._specs = {spec.agent_id: spec for spec in specs}
        default_specs = [spec for spec in self._specs.values() if spec.is_default]
        if len(default_specs) > 1:
            raise ValueError("只能配置一个默认智能体")
        self._default_agent_id = default_specs[0].agent_id if default_specs else None

    def list_specs(self) -> list[AgentSpec]:
        """返回全部可用智能体定义。

        Args:
            无。

        Returns:
            按默认智能体优先排序的智能体定义列表。
        """
        specs = list(self._specs.values())
        specs.sort(key=lambda spec: (not spec.is_default, spec.agent_id))
        return specs

    def get(self, agent_id: str) -> AgentSpec:
        """按 ID 获取智能体定义。

        Args:
            agent_id: 智能体 ID。

        Returns:
            对应智能体定义。

        Raises:
            KeyError: 智能体 ID 不存在。
        """
        try:
            return self._specs[agent_id]
        except KeyError as exc:
            raise KeyError(f"未知智能体: {agent_id}") from exc

    def resolve(self, agent_id: str | None) -> AgentSpec:
        """解析请求中的智能体 ID，未指定时使用默认智能体。

        Args:
            agent_id: 请求中的可选智能体 ID。

        Returns:
            对应智能体定义。

        Raises:
            KeyError: 智能体 ID 不存在或未配置默认智能体。
        """
        resolved = agent_id or self._default_agent_id
        if not resolved:
            raise KeyError("未指定智能体且没有默认智能体")
        return self.get(resolved)


class AgentRuntimeRegistry:
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
        spec: AgentSpec,
        checkpointer: Any | None,
        store: Any | None,
    ) -> Any:
        """懒加载并缓存指定智能体的图。

        Args:
            request: 当前 FastAPI 请求。
            spec: 智能体定义。
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。

        Returns:
            已装配的 LangGraph 图。
        """
        app_id = id(request.app)
        cache_key = (app_id, spec.agent_id, id(checkpointer), id(store))
        cached = self._graphs.get(cache_key)
        if cached is not None:
            return cached

        async with self._lock_for(app_id, spec.agent_id):
            cached = self._graphs.get(cache_key)
            if cached is None:
                cached = spec.graph_factory(checkpointer, store)
                self._graphs[cache_key] = cached
        return cached

    async def get_manager(
        self,
        request: Request,
        spec: AgentSpec,
        graph: Any,
        run_store: RunStore,
    ) -> AgentRunManager:
        """懒加载并缓存指定智能体的 Run 管理器。

        Args:
            request: 当前 FastAPI 请求。
            spec: 智能体定义。
            graph: 已装配的 LangGraph 图。
            run_store: AG-UI Run 存储。

        Returns:
            指定智能体的 Run 管理器。
        """
        app_id = id(request.app)
        cache_key = (app_id, spec.agent_id, id(graph), id(run_store))
        cached = self._managers.get(cache_key)
        if cached is not None:
            return cached

        async with self._lock_for(app_id, spec.agent_id):
            cached = self._managers.get(cache_key)
            if cached is None:
                cached = AgentRunManager(
                    graph,
                    store=run_store,
                    agent_id=spec.agent_id,
                )
                self._managers[cache_key] = cached
        return cached


def build_default_registry() -> AgentRegistry:
    """构建 DeepClaw 默认智能体注册表。

    Args:
        无。

    Returns:
        包含通用 Agent 与 RAG Agent 的注册表。
    """

    def build_agent_graph(checkpointer: Any | None, store: Any | None) -> Any:
        """构建通用 Agent 图。

        Args:
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。

        Returns:
            通用 Agent 图。
        """
        return Agent(
            deep_agent=True,
            checkpointer=checkpointer,
            store=store,
        ).get_agent()

    return AgentRegistry(
        [
            AgentSpec(
                agent_id="agent",
                name="通用智能体",
                description="通用工具调用、MCP 与深度思考",
                allowed_state_keys=frozenset(
                    {"internet_search", "deep_thinking", "mcp_config"}
                ),
                graph_factory=build_agent_graph,
                capabilities=("mcp", "deep_thinking", "internet_search"),
                is_default=True,
            ),
            AgentSpec(
                agent_id="rag",
                name="知识库问答",
                description="基于知识库检索和生成",
                allowed_state_keys=frozenset(
                    {"index_name", "graph_name", "internet_search", "deep_thinking"}
                ),
                graph_factory=create_rag_agent,
                capabilities=(
                    "knowledge_base",
                    "deep_thinking",
                    "internet_search",
                ),
            ),
        ]
    )
