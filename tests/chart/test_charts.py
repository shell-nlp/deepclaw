from deepclaw.middleware.chart.engine import render_chart


class TestChartBasic:
    """基础图表渲染测试"""

    def test_bar_chart(self):
        url = render_chart({
            "chart_type": "bar",
            "data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}],
            "title": "Test Bar",
        })
        assert url.startswith("http://") or url.startswith("/charts/")
        assert url.endswith(".png")

    def test_line_chart(self):
        url = render_chart({
            "chart_type": "line",
            "data": [{"time": "2020", "value": 10}, {"time": "2021", "value": 20}],
        })
        assert url.endswith(".png")

    def test_pie_chart(self):
        url = render_chart({
            "chart_type": "pie",
            "data": [{"category": "A", "value": 30}, {"category": "B", "value": 70}],
        })
        assert url.endswith(".png")

    def test_pie_donut_chart(self):
        """环形图"""
        url = render_chart({
            "chart_type": "pie",
            "data": [{"category": "A", "value": 30}, {"category": "B", "value": 70}],
            "innerRadius": 0.6,
        })
        assert url.endswith(".png")

    def test_column_chart(self):
        url = render_chart({
            "chart_type": "column",
            "data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}],
        })
        assert url.endswith(".png")

    def test_scatter_chart(self):
        url = render_chart({
            "chart_type": "scatter",
            "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
        })
        assert url.endswith(".png")

    def test_area_chart(self):
        url = render_chart({
            "chart_type": "area",
            "data": [{"time": "2020", "value": 10}, {"time": "2021", "value": 20}],
        })
        assert url.endswith(".png")

    def test_histogram_chart(self):
        url = render_chart({
            "chart_type": "histogram",
            "data": [1, 2, 2, 3, 3, 3, 4, 4, 5],
        })
        assert url.endswith(".png")

    def test_histogram_dict_data(self):
        """字典列表格式的直方图数据"""
        url = render_chart({
            "chart_type": "histogram",
            "data": [{"value": 1}, {"value": 2}, {"value": 2}],
        })
        assert url.endswith(".png")

    def test_funnel_chart(self):
        url = render_chart({
            "chart_type": "funnel",
            "data": [
                {"stage": "浏览", "value": 1000},
                {"stage": "点击", "value": 500},
                {"stage": "转化", "value": 100},
            ],
        })
        assert url.endswith(".png")

    def test_radar_chart(self):
        url = render_chart({
            "chart_type": "radar",
            "data": [
                {"item": "速度", "score": 80},
                {"item": "力量", "score": 60},
                {"item": "技巧", "score": 90},
            ],
        })
        assert url.endswith(".png")

    def test_radar_grouped(self):
        """分组雷达图"""
        url = render_chart({
            "chart_type": "radar",
            "data": [
                {"item": "速度", "score": 80, "group": "A"},
                {"item": "力量", "score": 60, "group": "A"},
                {"item": "技巧", "score": 90, "group": "A"},
                {"item": "速度", "score": 70, "group": "B"},
                {"item": "力量", "score": 80, "group": "B"},
                {"item": "技巧", "score": 60, "group": "B"},
            ],
        })
        assert url.endswith(".png")

    def test_grouped_bar(self):
        """分组柱状图"""
        url = render_chart({
            "chart_type": "bar",
            "data": [
                {"category": "北京", "value": 100, "group": "2023"},
                {"category": "上海", "value": 90, "group": "2023"},
                {"category": "北京", "value": 120, "group": "2024"},
                {"category": "上海", "value": 110, "group": "2024"},
            ],
            "group": True,
        })
        assert url.endswith(".png")

    def test_all_chart_types(self):
        """验证 9 种图表类型均可渲染"""
        from deepclaw.middleware.chart.charts import CHART_RENDERERS
        assert len(CHART_RENDERERS) == 9
        assert set(CHART_RENDERERS.keys()) == {
            "bar", "line", "pie", "column", "scatter",
            "area", "histogram", "funnel", "radar",
        }
