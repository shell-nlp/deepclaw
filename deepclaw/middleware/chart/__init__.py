"""图表生成模块。包含图表渲染引擎和 LangChain AgentMiddleware 适配。

用法::

    from deepclaw.middleware.chart import ChartMiddleware

    middleware = ChartMiddleware()
"""

from deepclaw.middleware.chart.charts import ALL_CHARTS, CHART_MAP, ChartDef, register
from deepclaw.middleware.chart.engine import render_chart
from deepclaw.middleware.chart.middleware import ChartMiddleware

__all__ = [
    "ALL_CHARTS",
    "CHART_MAP",
    "ChartDef",
    "ChartMiddleware",
    "register",
    "render_chart",
]
