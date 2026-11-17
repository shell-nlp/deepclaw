import matplotlib.pyplot as plt
import pytest

from deepclaw.middleware.chart.charts import (area, column, line, pie, radar, scatter)
from deepclaw.middleware.chart.engine import render_chart

from deepclaw.common.object_storage import LocalObjectStorage
from deepclaw.middleware.chart import utils
from deepclaw.middleware.chart import storage as chart_storage
from deepclaw.middleware.chart.charts import bar, funnel
from deepclaw.middleware.chart.middleware import CHART_SYSTEM_PROMPT, CHART_TOOL_DESCRIPTION


def test_save_chart_to_workspace_returns_absolute_url(tmp_path, monkeypatch):
    object_storage = LocalObjectStorage(tmp_path)
    monkeypatch.setattr(
        chart_storage,
        "get_chart_object_storage",
        lambda: object_storage,
    )
    monkeypatch.setattr(utils.settings, "CHART_PUBLIC_URL", "https://charts.example.com/")

    figure = plt.figure()
    chart_url = utils.save_chart_to_workspace(figure)

    assert chart_url.startswith("https://charts.example.com/charts/")
    file_name = chart_url.rsplit("/", maxsplit=1)[-1]
    assert object_storage.exists(
        "chart-assets",
        f"charts/{file_name}",
    )


def test_save_chart_to_workspace_returns_relative_url_without_public_url(tmp_path, monkeypatch):
    object_storage = LocalObjectStorage(tmp_path)
    monkeypatch.setattr(
        chart_storage,
        "get_chart_object_storage",
        lambda: object_storage,
    )
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
    assert [text.get_text() for text in legend.get_texts()] == [
        "数据项一: 60 (60%)",
        "数据项二: 40 (40%)",
    ]
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
    assert [text.get_text() for text in legend.get_texts()] == ["数据: 25000 (100%)"]
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


def test_grouped_bar_separates_quantity_and_rate_axes(monkeypatch):
    """校验数量与处理率使用独立横轴绘制。

    Args:
        monkeypatch: Pytest 的属性替换工具。
    """
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
            {"category": "刘阳", "value": 165, "group": "商机数量"},
            {"category": "张晓博", "value": 214, "group": "商机数量"},
            {"category": "刘阳", "value": 5.45, "group": "处理率(%)"},
            {"category": "张晓博", "value": 10.75, "group": "处理率(%)"},
        ],
        "width": 800,
        "height": 600,
        "axisXTitle": "分包人员",
        "axisYTitle": "商机数量（个）/ 处理率（%）",
        "stack": None,
    })

    figure = captured["figure"]
    primary_axis, rate_axis = figure.axes
    assert primary_axis.get_xlabel() == "商机数量"
    assert primary_axis.get_ylabel() == "分包人员"
    assert rate_axis.get_xlabel() == "处理率(%)"
    assert {text.get_text() for text in [*primary_axis.texts, *rate_axis.texts]} == {"165", "214", "5.45", "10.75"}
    plt.close(figure)

def test_setup_chinese_font_detects_wqy_zenhei(monkeypatch):
    """验证 WenQuanYi Zen Hei 字体族可被自动识别。

    Args:
        monkeypatch: pytest 提供的运行时属性替换工具。
    """
    font_entry = type("FontEntry", (), {"name": "WenQuanYi Zen Hei"})()
    monkeypatch.setattr(utils.fm.fontManager, "ttflist", [font_entry])

    assert utils.setup_chinese_font() == "WenQuanYi Zen Hei"


def test_finalize_chart_layout_protects_data_label_bounds():
    """验证统一布局函数为数据标签保留坐标轴边界。

    Args:
        无。
    """
    vertical_figure, vertical_axis = plt.subplots()
    vertical_axis.plot([0, 1], [0, 100])
    utils.finalize_chart_layout(
        vertical_figure,
        vertical_label_axes=(vertical_axis,),
    )
    assert vertical_axis.get_ylim()[1] > 100
    plt.close(vertical_figure)

    horizontal_figure, horizontal_axis = plt.subplots()
    horizontal_axis.barh([0, 1], [0, 100])
    utils.finalize_chart_layout(
        horizontal_figure,
        horizontal_label_axes=(horizontal_axis,),
    )
    assert horizontal_axis.get_xlim()[1] > 100
    plt.close(horizontal_figure)


DENSE_CATEGORIES = [f"郑州市第{i + 1}业务管理区域" for i in range(14)]
DENSE_TIMES = [f"2026-01-{i + 1:02d}" for i in range(24)]
DENSE_GROUPS = ["受理业务", "已完成业务", "待处理业务"]
DENSE_CASES = {
    "column": {
        "data": [
            {"category": category, "group": group, "value": 100 + index * 2 + offset}
            for offset, group in enumerate(DENSE_GROUPS)
            for index, category in enumerate(DENSE_CATEGORIES)
        ]
    },
    "line": {
        "data": [
            {"time": moment, "group": group, "value": 100 + index * 2 + offset}
            for offset, group in enumerate(DENSE_GROUPS)
            for index, moment in enumerate(DENSE_TIMES)
        ]
    },
    "area": {
        "data": [
            {"time": moment, "group": group, "value": 100 + index * 2 + offset}
            for offset, group in enumerate(DENSE_GROUPS)
            for index, moment in enumerate(DENSE_TIMES)
        ]
    },
    "pie": {
        "data": [
            {"category": category, "value": 1000 if index == 0 else 1}
            for index, category in enumerate(DENSE_CATEGORIES)
        ]
    },
    "radar": {
        "data": [
            {"item": f"业务能力评估维度{index + 1}", "group": group, "score": 60 + index + offset}
            for offset, group in enumerate(DENSE_GROUPS)
            for index in range(12)
        ]
    },
    "scatter": {
        "data": [
            {"x": index, "y": 200 + index * 4 + offset, "group": f"第{offset + 1}业务受理团队"}
            for offset in range(12)
            for index in range(15)
        ]
    },
}
DENSE_MODULES = {
    "column": column,
    "line": line,
    "area": area,
    "pie": pie,
    "radar": radar,
    "scatter": scatter,
}


def _overlapping_pairs(texts, renderer):
    """统计可见文本的矩形重叠对数。

    Args:
        texts: 待检查的 Matplotlib 文本对象。
        renderer: 当前图形渲染器。

    Returns:
        int: 发生重叠的文本对数量。
    """
    boxes = [
        text.get_window_extent(renderer)
        for text in texts
        if text.get_visible() and text.get_text().strip()
    ]
    return sum(
        1
        for index, first in enumerate(boxes)
        for second in boxes[index + 1:]
        if first.overlaps(second)
    )


@pytest.mark.parametrize("chart_type", DENSE_CASES)
def test_dense_chart_layout_keeps_labels_readable(monkeypatch, chart_type):
    """校验密集数据的标签、刻度和图例不重叠，且图元数量不变。

    Args:
        monkeypatch: Pytest 的属性替换工具。
        chart_type: 当前测试的图表类型。
    """
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 当前图表的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/dense.png"

    module = DENSE_MODULES[chart_type]
    monkeypatch.setattr(module, "save_chart_to_workspace", capture_chart)
    params = {
        **DENSE_CASES[chart_type],
        "chart_type": chart_type,
        "width": 600,
        "height": 400,
        "title": f"{chart_type} 密集数据检查",
    }
    render_chart(params)

    figure = captured["figure"]
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    for axis in figure.axes:
        assert _overlapping_pairs(axis.texts, renderer) == 0
        assert _overlapping_pairs(axis.get_xticklabels(), renderer) == 0
        legend = axis.get_legend()
        if legend is not None:
            legend_box = legend.get_window_extent(renderer)
            assert not legend_box.overlaps(axis.get_window_extent(renderer))
            assert not legend_box.overlaps(axis.title.get_window_extent(renderer))

    axis = figure.axes[0]
    rows = DENSE_CASES[chart_type]["data"]
    if chart_type == "line":
        assert len(axis.lines) == 3
        assert sum(len(line.get_xdata()) for line in axis.lines) == len(rows)
        assert sorted(value for line in axis.lines for value in line.get_ydata()) == sorted(
            row["value"] for row in rows
        )
        assert 1 < len(axis.get_xticks()) < len(DENSE_TIMES)
    elif chart_type == "pie":
        assert len(axis.patches) == len(rows)
        texts = [text.get_text() for text in axis.get_legend().get_texts()]
        assert len(texts) == len(rows)
        assert all("%" in text for text in texts)
        assert all(DENSE_CATEGORIES[index] in text for index, text in enumerate(texts))
    elif chart_type == "radar":
        assert len(axis.lines) == 3
        assert sorted(value for line in axis.lines for value in line.get_ydata()[:-1]) == sorted(
            row["score"] for row in rows
        )
    elif chart_type == "scatter":
        points = [point for collection in axis.collections for point in collection.get_offsets()]
        assert len(points) == len(rows)
        assert len(axis.get_legend().get_texts()) == 12
    elif chart_type == "column":
        assert len(axis.patches) == len(rows)
    plt.close(figure)


@pytest.mark.parametrize("chart_type", DENSE_CASES)
def test_small_canvas_and_long_title_stay_readable(monkeypatch, chart_type):
    """校验极小画布和超长标题会自动扩展画布并换行。

    Args:
        monkeypatch: Pytest 的属性替换工具。
        chart_type: 当前测试的图表类型。
    """
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 当前图表的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/small.png"

    module = DENSE_MODULES[chart_type]
    monkeypatch.setattr(module, "save_chart_to_workspace", capture_chart)
    render_chart(
        {
            **DENSE_CASES[chart_type],
            "chart_type": chart_type,
            "width": 100,
            "height": 100,
            "title": "业务统计对比与转化情况分析" * 8,
        }
    )

    figure = captured["figure"]
    assert figure.get_figwidth() >= 6
    assert figure.get_figheight() >= 4
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    for axis in figure.axes:
        assert "\n" in axis.get_title()
        assert _overlapping_pairs(axis.texts, renderer) == 0
    plt.close(figure)


def test_narrow_donut_moves_percentages_to_legend(monkeypatch):
    """校验窄环形图不再在扇区内强行标注百分比。

    Args:
        monkeypatch: Pytest 的属性替换工具。
    """
    captured = {}

    def capture_chart(figure):
        """保存待断言的图表对象。

        Args:
            figure: 当前图表的 Matplotlib 图形对象。
        """
        captured["figure"] = figure
        return "/charts/donut.png"

    monkeypatch.setattr(pie, "save_chart_to_workspace", capture_chart)
    pie.render(
        {
            "data": [{"category": "甲", "value": 80}, {"category": "乙", "value": 20}],
            "width": 800,
            "height": 600,
            "innerRadius": 0.9,
        }
    )

    axis = captured["figure"].axes[0]
    assert not any(text.get_text() for text in axis.texts)
    assert len(axis.patches) == 2
    assert all("%" in text.get_text() for text in axis.get_legend().get_texts())
    plt.close(captured["figure"])
