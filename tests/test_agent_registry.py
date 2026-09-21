import pytest

from deepclaw.agent_registry import Agent, AgentRegistry


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
