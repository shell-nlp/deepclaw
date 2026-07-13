"""图表生成模块。包含图表渲染引擎和 LangChain AgentMiddleware 适配。

用法::

    from deepclaw.middleware.chart import ChartMiddleware

    middleware = ChartMiddleware()
"""

from deepclaw.middleware.chart.charts import CHART_RENDERERS, ChartDef, ChartSchema
from deepclaw.middleware.chart.engine import render_chart
from deepclaw.middleware.chart.middleware import ChartMiddleware

__all__ = [
    "CHART_RENDERERS",
    "ChartDef",
    "ChartMiddleware",
    "ChartSchema",
    "render_chart",
]
