from pathlib import Path

import pytest
from pydantic import ValidationError

from deepclaw.middleware.chart.engine import render_chart
from deepclaw.settings import settings


class TestChartBasic:
    """基础图表渲染测试"""

    def test_bar_chart(self, tmp_path, monkeypatch):
        """验证默认使用相对地址并实际写出 PNG 文件。

        Args:
            tmp_path: pytest 提供的临时目录。
            monkeypatch: pytest 提供的属性替换工具。
        """
        monkeypatch.setattr(settings, "CHART_PUBLIC_URL", "")
        url = render_chart({
            "chart_type": "bar",
            "data": [{"category": "A", "value": 10}, {"category": "B", "value": 20}],
            "title": "Test Bar",
        })
        assert url.startswith("/charts/")
        assert url.endswith(".png")
        chart_file = tmp_path / "charts" / Path(url).name
        assert chart_file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

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


class TestChartValidation:
    """图表输入校验测试。"""

    @pytest.mark.parametrize("params", [
        {"chart_type": "radar", "data": []},
        {"chart_type": "bar", "data": [{"value": 1}]},
        {"chart_type": "histogram", "data": [1, 2], "bins": 0},
        {"chart_type": "pie", "data": [{"category": "A", "value": 0}]},
        {
            "chart_type": "bar",
            "data": [
                {"category": "A", "group": "G", "value": 1},
                {"category": "A", "group": "G", "value": 2},
            ],
        },
    ])
    def test_invalid_chart_data_returns_validation_error(self, params):
        """验证无效数据在渲染前被拦截。

        Args:
            params: 参数化传入的非法图表参数。
        """
        with pytest.raises(ValidationError):
            render_chart(params)

    def test_funnel_uses_largest_value_as_normalization_reference(self):
        """验证漏斗首项不是最大值时仍可生成图表。

        Args:
            无。
        """
        url = render_chart({
            "chart_type": "funnel",
            "data": [{"stage": "访问", "value": 10}, {"stage": "转化", "value": 20}],
        })
        assert url.endswith(".png")
