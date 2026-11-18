"""通用 Agent 公共能力测试。"""

from __future__ import annotations

from deepclaw.agents.general.agent import GeneralAgent


def test_general_agent_exposes_common_middleware() -> None:
    """验证通用中间件包含运行时所需的基础能力。

    HumanInTheLoopMiddleware 属于公共中间件：南阳天气与 ask_user 需要走标准
    HITL 中断，由 RUN_FINISHED.outcome 暴露给前端审批。

    Args:
        无。
    """
    common_names = [
        type(middleware).__name__
        for middleware in GeneralAgent.get_common_middleware()
    ]

    assert {
        "RecommendedQuestionsMiddleware",
        "BusinessMiddleware",
        "MCPMiddleware",
        "DeviceToolsMiddleware",
        "HumanInTheLoopMiddleware",
        "ChartMiddleware",
    } == set(common_names)


def test_general_agent_exposes_common_tools() -> None:
    """验证通用工具集合覆盖天气、抓取、提问与知识库检索。

    Args:
        无。
    """
    common_tool_names = {
        getattr(tool, "name", "") for tool in GeneralAgent.get_common_tools()
    }

    assert {"get_weather", "web_fetch", "ask_user", "retrieve_context"} == common_tool_names


def test_general_agent_build_agent_accepts_extra_tools() -> None:
    """验证额外工具通过 build_agent 的 tools 参数独立组合。

    Args:
        无。
    """
    signature = __import__("inspect").signature(GeneralAgent.build_agent)

    assert "tools" in signature.parameters
    assert signature.parameters["tools"].default is None
    assert not hasattr(GeneralAgent, "get_agent_tools")


def test_general_agent_exposes_knowledge_retrieval_tool() -> None:
    """通用 Agent 以工具方式支持知识库检索。

    Args:
        无。
    """
    common_tool_names = {
        getattr(tool, "name", "") for tool in GeneralAgent.get_common_tools()
    }

    assert "retrieve_context" in common_tool_names


def test_general_agent_accepts_index_names_state() -> None:
    """通用 Agent 需要接收 index_names，retrieve_context 才能按库检索。

    Args:
        无。
    """
    assert "index_names" in GeneralAgent.allowed_state_keys
