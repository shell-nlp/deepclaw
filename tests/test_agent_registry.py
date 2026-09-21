import asyncio

import pytest
from fastapi import FastAPI

from deepclaw.agent_registry import Agent, AgentRegistry
from deepclaw.web_backend.agui.runtime import AgentRuntimeCache


class DummyAgent(Agent):
    """测试用智能体定义。"""

    agent_id = "dummy"
    name = "测试智能体"
    description = "用于验证自动发现与注册表行为"
    capabilities = frozenset({"test"})
    allowed_state_keys = frozenset({"deep_thinking"})
    is_default = True

    @classmethod
    def build_agent(cls, *, checkpointer=None, store=None):
        """返回测试图占位对象。

        Args:
            checkpointer: 检查点存储。
            store: 长期存储。
        """
        return object()


def test_discover_finds_project_agents():
    """验证自动发现能识别项目内置智能体。"""
    registry = AgentRegistry.discover()

    assert {agent.agent_id for agent in registry.list_agents()} == {
        "agent",
        "rag",
    }
    assert registry.resolve(None).agent_id == "agent"


def test_registry_rejects_duplicate_agent_id():
    """验证重复 agent_id 会被拒绝。"""
    with pytest.raises(ValueError, match="重复"):
        AgentRegistry([DummyAgent, DummyAgent])


def test_runtime_cache_preload_builds_agents(monkeypatch):
    """验证运行时缓存会预热全部智能体。

    Args:
        monkeypatch: pytest 补丁工具。
    """
    from deepclaw.web_backend.agui import runtime as runtime_module

    class FakeRunManager:
        """测试用 Run 管理器。"""

        def __init__(self, graph, store=None, agent_id=None):
            """初始化测试用 Run 管理器。

            Args:
                graph: 已构建的图。
                store: Run 存储。
                agent_id: 智能体 ID。
            """
            self.graph = graph
            self.store = store
            self.agent_id = agent_id

    class CountingAgent(Agent):
        """记录构建次数的测试智能体。"""

        agent_id = "counting"
        name = "计数智能体"
        description = "用于验证运行时缓存预热"
        build_calls = 0

        @classmethod
        def build_agent(cls, *, checkpointer=None, store=None):
            """返回带构建次数的测试图。

            Args:
                checkpointer: 检查点存储。
                store: 长期存储。
            """
            cls.build_calls += 1
            return {
                "checkpointer": checkpointer,
                "store": store,
            }

    monkeypatch.setattr(runtime_module, "AgentRunManager", FakeRunManager)
    cache = AgentRuntimeCache()
    app = FastAPI()

    async def run():
        """执行预热并返回缓存图。

        Args:
            无。
        """
        await cache.preload(
            app=app,
            agents=[CountingAgent],
            checkpointer="checkpointer",
            store="store",
            run_store="run-store",
        )
        return await cache.get_graph(
            app,
            CountingAgent,
            "checkpointer",
            "store",
        )

    graph = asyncio.run(run())
    assert graph == {
        "checkpointer": "checkpointer",
        "store": "store",
    }
    assert CountingAgent.build_calls == 1
