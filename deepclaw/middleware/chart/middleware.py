from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from loguru import logger
from pydantic import ValidationError

from deepclaw.middleware.chart.charts import CHART_TYPE_DESCRIPTIONS, ChartSchema
from deepclaw.middleware.chart.engine import render_chart

CHART_TOOL_DESCRIPTION = (
    "生成统计图表（9 种类型可用）。根据 chart_type 选择图表类型，传入对应格式的数据。\n\n"
    + "图表类型说明:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CHART_TYPE_DESCRIPTIONS.items())
    + "\n\n数据格式:\n"
    + "- bar/column/pie/funnel: [{'category': 'A', 'value': 10, 'group': '组别'}, ...]\n"
    + "- line/area: [{'time': '2020', 'value': 10, 'group': '组别'}, ...]\n"
    + "- scatter: [{'x': 1, 'y': 2, 'group': '组别'}, ...]\n"
    + "- radar: [{'item': '速度', 'score': 80, 'group': '组别'}, ...]\n"
    + "- histogram: [1, 2, 3] 或 [{'value': 1}, ...]"
)


@tool("generate_chart", description=CHART_TOOL_DESCRIPTION, args_schema=ChartSchema)
def chart_tool(**kwargs: Any) -> str:
    """生成图表"""
    url = render_chart(kwargs)
    return f"![]({url})"


class ChartMiddleware(AgentMiddleware):
    """图表生成中间件，提供统一 generate_chart 工具给 Agent。"""

    def get_tools(self):
        return [chart_tool]

    async def awrap_model_call(self, request, handler):
        extend_tools = [t for t in request.tools if t.name != "generate_chart"]
        return await handler(request.override(tools=extend_tools + self.get_tools()))

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool_call["name"] != "generate_chart":
            return await handler(request)
        try:
            url = render_chart(request.tool_call["args"])
            return ToolMessage(
                content=f"![]({url})",
                tool_call_id=request.tool_call["id"],
            )
        except ValidationError as e:
            logger.warning("图表参数验证失败: error={}", e.errors())
            return ToolMessage(
                content=f"错误: 参数验证失败 - {e.errors()}. 请参考工具描述使用正确的数据格式。",
                tool_call_id=request.tool_call["id"],
            )
        except Exception as e:
            logger.error("图表生成失败: error={}", repr(e))
            return ToolMessage(
                content=f"错误: 图表生成失败 - {e}.",
                tool_call_id=request.tool_call["id"],
            )
