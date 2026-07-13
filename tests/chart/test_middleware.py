from deepclaw.middleware.chart import ChartMiddleware


def test_middleware_tools_class_var():
    assert len(ChartMiddleware.tools) == 1
    assert ChartMiddleware.tools[0].name == "generate_chart"


def test_chart_tool_schema():
    from deepclaw.middleware.chart.middleware import chart_tool
    assert chart_tool.name == "generate_chart"
    assert hasattr(chart_tool, "args_schema")
