"""通用 Agent 公共能力测试。"""

from __future__ import annotations

from deepclaw.agents.general.agent import GeneralAgent


def test_general_agent_exposes_common_middleware() -> None:
    """验证通用中间件包含运行时所需的基础能力。

    Args:
        无。
    """
    common_names = {
        type(middleware).__name__
        for middleware in GeneralAgent.get_common_middleware()
    }

    assert {
        "RecommendedQuestionsMiddleware",
        "BusinessMiddleware",
        "MCPMiddleware",
    }.issubset(common_names)
    assert "HumanInTheLoopMiddleware" not in common_names


def test_general_agent_exposes_common_tools() -> None:
    """验证通用工具与调用方额外工具可以分开组合。

    Args:
        无。
    """
    common_tool_names = {
        getattr(tool, "name", "") for tool in GeneralAgent.get_common_tools()
    }

    class ExtraTool:
        """测试用额外工具。"""

        name = "extra_tool"

    extra_tools = GeneralAgent.get_agent_tools([ExtraTool()])

    assert {"get_weather", "web_fetch", "ask_user"}.issubset(common_tool_names)
    assert len(extra_tools) == 1
    assert extra_tools[0].name == "extra_tool"
