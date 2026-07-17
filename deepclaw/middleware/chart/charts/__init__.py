"""图表注册表和所有图表类型。"""

from collections.abc import Callable

from deepclaw.middleware.chart.charts.registry import ChartDef

# 导入 render 函数
from deepclaw.middleware.chart.charts.bar import render as _render_bar
from deepclaw.middleware.chart.charts.line import render as _render_line
from deepclaw.middleware.chart.charts.pie import render as _render_pie
from deepclaw.middleware.chart.charts.column import render as _render_column
from deepclaw.middleware.chart.charts.scatter import render as _render_scatter
from deepclaw.middleware.chart.charts.area import render as _render_area
from deepclaw.middleware.chart.charts.histogram import render as _render_histogram
from deepclaw.middleware.chart.charts.funnel import render as _render_funnel
from deepclaw.middleware.chart.charts.radar import render as _render_radar

from deepclaw.middleware.chart.schemas import CHART_TYPES, CHART_TYPE_DESCRIPTIONS, ChartSchema

CHART_RENDERERS: dict[str, Callable[[dict], str]] = {
    "bar": _render_bar,
    "line": _render_line,
    "pie": _render_pie,
    "column": _render_column,
    "scatter": _render_scatter,
    "area": _render_area,
    "histogram": _render_histogram,
    "funnel": _render_funnel,
    "radar": _render_radar,
}

__all__ = [
    "CHART_TYPES",
    "CHART_TYPE_DESCRIPTIONS",
    "CHART_RENDERERS",
    "ChartDef",
    "ChartSchema",
]
