import matplotlib.pyplot as plt

from deepclaw.middleware.chart import utils
from deepclaw.middleware.chart.charts import bar, funnel, line, pie
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
        assert "不得调整数值量级" in prompt
        assert "不做万、百万或亿换算" in prompt


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
    assert [text.get_text() for text in legend.get_texts()] == ["数据项一", "数据项二"]
    assert {"60.0%", "40.0%"}.issubset({text.get_text() for text in axis.texts})
    plt.close(captured["figure"])


def test_bar_chart_keeps_original_value_labels(monkeypatch):
    """校验条形图标签保持原始数值。"""
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
    assert "25000" in {text.get_text() for text in axis.texts}
    assert axis.get_xlabel() == ""
    assert small_value_label.xy[0] > 0
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
    assert {text.get_text() for text in axis.texts} == {"10", "2500000", "12.5"}
    assert axis.get_ylabel() == ""
    plt.close(captured["figure"])








def test_pie_and_funnel_chart_keep_original_values(monkeypatch):
    """校验饼图图例和漏斗图保留原始数值。"""
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
    assert [text.get_text() for text in legend.get_texts()] == ["数据"]
    plt.close(captured["figure"])

    monkeypatch.setattr(funnel, "save_chart_to_workspace", capture_chart)
    funnel.render({
        "data": [{"stage": "阶段", "value": 2_500_000}],
        "width": 800,
        "height": 600,
    })
    assert any("2500000" in text.get_text() for text in captured["figure"].axes[0].texts)
    plt.close(captured["figure"])


def test_format_number_uses_scientific_notation_for_large_values():
    """校验过长数值使用正确的科学计数法。"""
    assert utils.format_number(123_456_789) == "123456789"
    assert utils.format_number(10**20) == "1e+20"
