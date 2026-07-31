"""通用中间件测试。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import ToolMessage


class FakeToolCallRequest:
    """最小化的工具调用请求替身。"""

    def __init__(self, name: str = "query_ontology_graph") -> None:
        """初始化工具调用标识。

        Args:
            name: 被调用的工具名称。
        """
        self.tool_call = {"id": "call_ontology", "name": name}


def test_business_middleware_returns_tool_error_message() -> None:
    """验证工具参数错误不会中断 Agent 任务。

    Args:
        无。
    """
    from deepclaw.middleware.common import BusinessMiddleware

    async def handler(request):
        """模拟工具执行抛出参数校验异常。

        Args:
            request: 当前工具调用请求。
        """
        _ = request
        raise ValueError("不要在 Cypher 中写 LIMIT；请使用工具的 limit 参数。")

    result = asyncio.run(
        BusinessMiddleware().awrap_tool_call(FakeToolCallRequest(), handler)
    )

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call_ontology"
    assert result.status == "error"
    assert "query_ontology_graph" in result.content
    assert "请使用工具的 limit 参数" in result.content


def test_business_middleware_keeps_successful_tool_result() -> None:
    """验证正常工具结果仍由原处理器返回。

    Args:
        无。
    """
    from deepclaw.middleware.common import BusinessMiddleware

    expected = ToolMessage(content="正常结果", tool_call_id="call_ontology")

    async def handler(request):
        """模拟工具执行成功。

        Args:
            request: 当前工具调用请求。

        Returns:
            正常工具消息。
        """
        _ = request
        return expected

    result = asyncio.run(
        BusinessMiddleware().awrap_tool_call(FakeToolCallRequest(), handler)
    )

    assert result is expected
