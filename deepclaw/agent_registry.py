from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Iterable


class Agent(ABC):
    """统一 AG-UI 可暴露的智能体基类。"""

    # 对外暴露的智能体 ID，也是 AG-UI 请求顶层 agentId 的取值。
    agent_id: ClassVar[str]
    # 前端展示名称。
    name: ClassVar[str]
    # 前端展示说明。
    description: ClassVar[str]
    # 当前智能体支持的能力标签，供前端按能力展示或启用功能。
    capabilities: ClassVar[frozenset[str]] = frozenset()
    # 允许从客户端 state 传入并写入 LangGraph state 的字段集合。
    allowed_state_keys: ClassVar[frozenset[str]] = frozenset()
    # 未显式指定 agentId 时是否作为默认智能体。
    is_default: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def build_agent(
        cls,
        *,
        checkpointer: Any | None = None,
        store: Any | None = None,
    ) -> Any:
        """构建当前智能体的 LangGraph 图。

        Args:
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。
        """
        raise NotImplementedError


class AgentRegistry:
    """自动发现、保存并按 ID 解析智能体类。"""

    def __init__(self, agents: Iterable[type[Agent]]) -> None:
        """初始化智能体注册表。

        Args:
            agents: 可用智能体类。
        """
        self._agents: dict[str, type[Agent]] = {}
        for agent in agents:
            self._register(agent)

        default_agents = [
            agent
            for agent in self._agents.values()
            if agent.is_default
        ]
        if len(default_agents) > 1:
            raise ValueError("只能配置一个默认智能体")
        self._default_agent_id = (
            default_agents[0].agent_id if default_agents else None
        )

    def _register(self, agent: type[Agent]) -> None:
        """校验并登记一个智能体类。

        Args:
            agent: 待登记的智能体类。

        Raises:
            TypeError: 智能体类型不合法。
            ValueError: 智能体元数据不合法或 ID 重复。
        """
        if not inspect.isclass(agent) or not issubclass(agent, Agent):
            raise TypeError("注册项必须是 Agent 子类")
        if inspect.isabstract(agent):
            raise TypeError("不能注册抽象智能体")

        agent_id = getattr(agent, "agent_id", "")
        name = getattr(agent, "name", "")
        description = getattr(agent, "description", "")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("智能体 agent_id 不能为空")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"智能体 {agent_id} 的 name 不能为空")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"智能体 {agent_id} 的 description 不能为空")
        if not callable(getattr(agent, "build_agent", None)):
            raise ValueError(f"智能体 {agent_id} 未实现 build_agent")
        if agent_id in self._agents:
            raise ValueError(f"智能体 ID 重复: {agent_id}")

        self._agents[agent_id] = agent

    @classmethod
    def discover(cls) -> AgentRegistry:
        """扫描 deepclaw.agents 下的 agent 模块并构建注册表。

        Args:
            无。

        Returns:
            自动发现得到的智能体注册表。

        Raises:
            ValueError: 未发现任何智能体类。
        """
        import deepclaw.agents as agents_package

        agents: list[type[Agent]] = []
        package_prefix = f"{agents_package.__name__}."
        for module_info in pkgutil.iter_modules(
            agents_package.__path__,
            prefix=package_prefix,
        ):
            if not module_info.ispkg:
                continue

            module_name = f"{module_info.name}.agent"
            if importlib.util.find_spec(module_name) is None:
                continue

            module = importlib.import_module(module_name)
            for value in vars(module).values():
                if not inspect.isclass(value):
                    continue
                if value is Agent or not issubclass(value, Agent):
                    continue
                if value.__module__ != module.__name__:
                    continue
                agents.append(value)

        if not agents:
            raise ValueError("未发现任何智能体类")
        return cls(agents)

    def list_agents(self) -> list[type[Agent]]:
        """返回全部智能体类。

        Args:
            无。

        Returns:
            按默认智能体优先排序的智能体类列表。
        """
        agents = list(self._agents.values())
        agents.sort(
            key=lambda agent: (
                not agent.is_default,
                agent.agent_id,
            )
        )
        return agents

    def get(self, agent_id: str) -> type[Agent]:
        """按 ID 获取智能体类。

        Args:
            agent_id: 智能体 ID。

        Returns:
            对应智能体类。

        Raises:
            KeyError: 智能体 ID 不存在。
        """
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"未知智能体: {agent_id}") from exc

    def resolve(self, agent_id: str | None) -> type[Agent]:
        """解析请求中的智能体 ID，未指定时使用默认智能体。

        Args:
            agent_id: 请求中的可选智能体 ID。

        Returns:
            对应智能体类。

        Raises:
            KeyError: 智能体 ID 不存在或未配置默认智能体。
        """
        resolved = agent_id or self._default_agent_id
        if not resolved:
            raise KeyError("未指定智能体且没有默认智能体")
        return self.get(resolved)
