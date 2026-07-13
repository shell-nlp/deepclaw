from deepclaw.middleware.chart import ChartMiddleware


def test_middleware_single_tool():
    mw = ChartMiddleware()
    tools = mw.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "generate_chart"


def test_chart_tool_schema():
    from deepclaw.middleware.chart.middleware import chart_tool
    assert chart_tool.name == "generate_chart"
    assert hasattr(chart_tool, "args_schema")
