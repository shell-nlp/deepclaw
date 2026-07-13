from deepclaw.middleware.chart import ChartMiddleware, ALL_CHARTS, CHART_MAP


def test_middleware_tools():
    mw = ChartMiddleware()
    tools = mw.get_tools()
    assert len(tools) == len(ALL_CHARTS)
    assert all(t.name.startswith("generate_") for t in tools)


def test_chart_map_complete():
    assert len(CHART_MAP) == 9
    assert "generate_pie_chart" in CHART_MAP
    assert "generate_radar_chart" in CHART_MAP
