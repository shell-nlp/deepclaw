import matplotlib
matplotlib.use("Agg")

from threading import RLock

import matplotlib.pyplot as plt

from deepclaw.middleware.chart.charts import CHART_RENDERERS, ChartSchema
from deepclaw.middleware.chart.utils import setup_chinese_font

_chinese_font: str | None = None
_render_lock = RLock()


def _get_font() -> str:
    """获取缓存的中文字体名称。"""
    global _chinese_font
    if _chinese_font is None:
        _chinese_font = setup_chinese_font()
    return _chinese_font


def render_chart(params: dict) -> str:
    """校验参数并在受保护的 Matplotlib 上下文中渲染图表。

    Args:
        params: 原始图表参数字典。

    Returns:
        str: 图表的可访问 URL 路径。
    """
    validated = ChartSchema(**params)
    data = validated.model_dump()
    chart_type = data["chart_type"]
    render_fn = CHART_RENDERERS.get(chart_type)
    if not render_fn:
        raise ValueError(f"未知图表类型: {chart_type}")
    with _render_lock, plt.rc_context({
        "font.sans-serif": [_get_font()],
        "axes.unicode_minus": False,
    }):
        return render_fn(data)
