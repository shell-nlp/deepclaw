from types import SimpleNamespace

from deepclaw.middleware.chart import ChartMiddleware
from deepclaw.middleware.chart.middleware import (
    CHART_PROMPT_MARKER,
    CHART_SYSTEM_PROMPT,
    CHART_TOOL_DESCRIPTION,
)
from langchain_core.messages import SystemMessage


def test_middleware_tools_class_var():
    assert len(ChartMiddleware.tools) == 1
    assert ChartMiddleware.tools[0].name == "generate_chart"


def test_chart_tool_schema():
    from deepclaw.middleware.chart.middleware import chart_tool
    assert chart_tool.name == "generate_chart"
    assert hasattr(chart_tool, "args_schema")


def test_chart_prompt_covers_final_answer_and_data_rules():
    """验证提示词要求展示图片、解读数据且不允许编造数据。

    Args:
        无。
    """
    assert "不得为了生成图表而编造" in CHART_SYSTEM_PROMPT
    assert "最终回答必须原样保留并展示该 Markdown 图片" in CHART_SYSTEM_PROMPT
    assert "关键结论" in CHART_SYSTEM_PROMPT
    assert "pie/funnel 的 value 必须非负" in CHART_TOOL_DESCRIPTION


def test_chart_prompt_is_not_injected_twice():
    """验证重复模型调用不会重复追加图表系统提示。

    Args:
        无。
    """
    middleware = ChartMiddleware()
    existing_message = SystemMessage(content=[{"type": "text", "text": CHART_SYSTEM_PROMPT}])
    request = SimpleNamespace(system_message=existing_message)

    result = middleware._override_system_message(request)

    assert result is existing_message
    assert CHART_PROMPT_MARKER in str(result.content)
