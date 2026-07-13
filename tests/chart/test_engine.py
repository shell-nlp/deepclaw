def test_engine_imports():
    import deepclaw.middleware.chart.engine as engine
    import deepclaw.middleware.chart.charts as charts

    assert hasattr(engine, "render_chart")
    assert hasattr(charts, "CHART_RENDERERS")
    assert hasattr(charts, "ChartSchema")
