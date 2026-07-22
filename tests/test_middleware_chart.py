import matplotlib.pyplot as plt
import pytest

from deepclaw.middleware.chart import utils
from deepclaw.middleware.chart.charts import area, bar, column, funnel, histogram, line, pie, radar, scatter
from deepclaw.middleware.chart.middleware import CHART_SYSTEM_PROMPT, CHART_TOOL_DESCRIPTION


def test_save_chart_to_workspace_returns_absolute_url(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "_CHARTS_DIR", tmp_path)
    monkeypatch.setattr(utils.settings, "CHART_PUBLIC_URL", "https://charts.example.com/")

    figure = plt.figure()
    chart_url = utils.save_chart_to_workspace(figure)

    assert chart_url.startswith("https://charts.example.com/charts/")
    assert (tmp_path / chart_url.rsplit("/", maxsplit=1)[-1]).is_file()


def test_save_chart_to_workspace_returns_relative_url_without_public_url(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "_CHARTS_DIR", tmp_path)
    monkeypatch.setattr(utils.settings, "CHART_PUBLIC_URL", "")

    chart_url = utils.save_chart_to_workspace(plt.figure())

    assert chart_url.startswith("/charts/")


def test_chart_prompts_require_original_values_without_model_scaling():
    """校验模型必须将原始数值传给图表工具。"""
    for prompt in (CHART_SYSTEM_PROMPT, CHART_TOOL_DESCRIPTION):
        assert "原始数值" in prompt
        assert "不得预先换算" in prompt


def test_bar_chart_sorts_descending_and_displays_values(monkeypatch):
    """校验条形图降序排列并显示数值标签。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 条形图的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/bar.png"

    monkeypatch.setattr(bar, "save_chart_to_workspace", capture_chart)

    chart_url = bar.render({
        "data": [
            {"category": "低", "value": 10},
            {"category": "高", "value": 30},
            {"category": "中", "value": 20},
        ],
        "width": 800,
        "height": 600,
        "stack": None,
    })

    axis = captured["figure"].axes[0]
    assert chart_url == "/charts/bar.png"
    assert [label.get_text() for label in axis.get_yticklabels()] == ["高", "中", "低"]
    assert axis.yaxis_inverted()
    assert {text.get_text() for text in axis.texts} == {"10", "20", "30"}
    plt.close(captured["figure"])


def test_pie_chart_displays_categories_in_legend(monkeypatch):
    """校验饼图通过图例展示数据项名称。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 饼图的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/pie.png"

    monkeypatch.setattr(pie, "save_chart_to_workspace", capture_chart)

    pie.render({
        "data": [
            {"category": "数据项一", "value": 60},
            {"category": "数据项二", "value": 40},
        ],
        "width": 800,
        "height": 600,
    })

    axis = captured["figure"].axes[0]
    legend = axis.get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == ["数据项一（60）", "数据项二（40）"]
    assert {"60.0%", "40.0%"}.issubset({text.get_text() for text in axis.texts})
    plt.close(captured["figure"])


def test_bar_chart_uses_wan_unit_and_keeps_small_value_label_on_axis_right(monkeypatch):
    """校验万级图表的小值标签保持在横轴右侧。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 条形图的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/bar.png"

    monkeypatch.setattr(bar, "save_chart_to_workspace", capture_chart)

    bar.render({
        "data": [
            {"category": "大值", "value": 25_000},
            {"category": "小值", "value": 5},
        ],
        "width": 800,
        "height": 600,
        "stack": None,
    })

    axis = captured["figure"].axes[0]
    small_value_label = next(text for text in axis.texts if text.get_text() == "5")
    assert axis.get_xlabel() == "数值（万）"
    assert small_value_label.xy[0] > 0
    assert all("e" not in label.get_text().lower() for label in axis.get_xticklabels())
    plt.close(captured["figure"])


@pytest.mark.parametrize(
    ("value", "expected_unit"),
    [(25_000, "万"), (2_500_000, "百万"), (250_000_000, "亿")],
)
def test_bar_chart_selects_scale_appropriate_unit(monkeypatch, value, expected_unit):
    """校验条形图按数据量级自动选择显示单位。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 条形图的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/bar.png"

    monkeypatch.setattr(bar, "save_chart_to_workspace", capture_chart)

    bar.render({
        "data": [{"category": "数据", "value": value}],
        "width": 800,
        "height": 600,
        "stack": None,
    })

    axis = captured["figure"].axes[0]
    assert axis.get_xlabel() == f"数值（{expected_unit}）"
    plt.close(captured["figure"])


def test_line_chart_displays_each_data_point_value(monkeypatch):
    """校验折线图为每个数据点显示数值标签。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 折线图的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/line.png"

    monkeypatch.setattr(line, "save_chart_to_workspace", capture_chart)

    line.render({
        "data": [
            {"time": "2026-01", "value": 10},
            {"time": "2026-02", "value": 2_500_000},
            {"time": "2026-03", "value": 12.5},
        ],
        "width": 800,
        "height": 600,
    })

    axis = captured["figure"].axes[0]
    assert {text.get_text() for text in axis.texts} == {"10", "2.5百万", "12.5"}
    assert axis.get_ylabel() == "数值（百万）"
    plt.close(captured["figure"])


@pytest.mark.parametrize(
    ("renderer", "data", "axis_name", "expected_label"),
    [
        (column, [{"category": "数据", "value": 2_500_000}], "y", "数值（百万）"),
        (area, [{"time": "2026-01", "value": 2_500_000}], "y", "数值（百万）"),
        (histogram, [1_000_000, 2_500_000], "x", "数值（百万）"),
        (radar, [{"item": "指标", "score": 250_000_000}], "y", "数值（亿）"),
    ],
)
def test_numeric_axis_charts_apply_auto_unit(monkeypatch, renderer, data, axis_name, expected_label):
    """校验数值轴图表统一应用自动单位换算。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/chart.png"

    monkeypatch.setattr(renderer, "save_chart_to_workspace", capture_chart)

    renderer.render({"data": data, "width": 800, "height": 600, "stack": None})

    axis = captured["figure"].axes[0]
    assert getattr(axis, f"get_{axis_name}label")() == expected_label
    plt.close(captured["figure"])


def test_scatter_chart_applies_units_to_both_numeric_axes(monkeypatch):
    """校验散点图分别为横纵数值轴标注自动单位。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/scatter.png"

    monkeypatch.setattr(scatter, "save_chart_to_workspace", capture_chart)

    scatter.render({
        "data": [{"x": 25_000, "y": 2_500_000}],
        "width": 800,
        "height": 600,
    })

    axis = captured["figure"].axes[0]
    assert axis.get_xlabel() == "X 值（万）"
    assert axis.get_ylabel() == "Y 值（百万）"
    plt.close(captured["figure"])


def test_pie_and_funnel_chart_display_auto_units(monkeypatch):
    """校验饼图图例和漏斗图数值文本显示自动单位。"""
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/chart.png"

    monkeypatch.setattr(pie, "save_chart_to_workspace", capture_chart)
    pie.render({
        "data": [{"category": "数据", "value": 25_000}],
        "width": 800,
        "height": 600,
    })
    legend = captured["figure"].axes[0].get_legend()
    assert legend is not None
    assert legend.get_title().get_text() == "数据项"
    assert [text.get_text() for text in legend.get_texts()] == ["数据（2.5万）"]
    plt.close(captured["figure"])

    monkeypatch.setattr(funnel, "save_chart_to_workspace", capture_chart)
    funnel.render({
        "data": [{"stage": "阶段", "value": 2_500_000}],
        "width": 800,
        "height": 600,
    })
    assert any("2.5百万" in text.get_text() for text in captured["figure"].axes[0].texts)
    plt.close(captured["figure"])
