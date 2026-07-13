import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from deepclaw.middleware.chart.charts import CHART_RENDERERS, ChartSchema
from deepclaw.middleware.chart.utils import setup_chinese_font

_chinese_font: str | None = None


def _get_font() -> str:
    """获取缓存的中文字体名称。"""
    global _chinese_font
    if _chinese_font is None:
        _chinese_font = setup_chinese_font()
    return _chinese_font


def render_chart(params: dict) -> str:
    """统一图表渲染入口，通过 ChartSchema 验证后根据 chart_type 派发。

    Parameters
    ----------
    params : dict
        原始图表参数字典

    Returns
    -------
    str
        图表的可访问 URL 路径
    """
    validated = ChartSchema(**params)
    data = validated.model_dump()
    chart_type = data["chart_type"]
    render_fn = CHART_RENDERERS.get(chart_type)
    if not render_fn:
        raise ValueError(f"未知图表类型: {chart_type}")
    plt.rcParams["font.sans-serif"] = [_get_font()]
    plt.rcParams["axes.unicode_minus"] = False
    return render_fn(data)
