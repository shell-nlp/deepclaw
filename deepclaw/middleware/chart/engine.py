import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from deepclaw.middleware.chart.charts import CHART_MAP
from deepclaw.middleware.chart.utils import setup_chinese_font

_chinese_font: str | None = None


def _get_font() -> str:
    """获取缓存的中文字体名称。"""
    global _chinese_font
    if _chinese_font is None:
        _chinese_font = setup_chinese_font()
    return _chinese_font


def render_chart(chart_type: str, params: dict) -> str:
    """统一图表渲染入口，根据类型查找注册的图表定义并执行渲染。

    Parameters
    ----------
    chart_type : str
        图表类型名称（需在 CHART_MAP 中注册）
    params : dict
        图表参数字典

    Returns
    -------
    str
        图表的可访问 URL 路径
    """
    chart_def = CHART_MAP.get(chart_type)
    if not chart_def:
        raise ValueError(f"未知图表类型: {chart_type}")
    validated = chart_def.schema(**params)
    plt.rcParams["font.sans-serif"] = [_get_font()]
    plt.rcParams["axes.unicode_minus"] = False
    return chart_def.render(validated.model_dump())
