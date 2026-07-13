from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool as langchain_tool
from loguru import logger
from pydantic import ValidationError

from deepclaw.middleware.chart.charts import ALL_CHARTS, CHART_MAP
from deepclaw.middleware.chart.engine import render_chart


def _make_chart_tool(cd):
    """根据 ChartDef 创建 LangChain 工具。"""
    @langchain_tool(cd.name, description=cd.description, args_schema=cd.schema)
    def chart_tool(**kwargs: Any) -> str:
        """生成图表"""
        url = render_chart(cd.name, kwargs)
        return f"![]({url})"
    return chart_tool


class ChartMiddleware(AgentMiddleware):
    """图表生成中间件，提供 9 种图表工具给 Agent。

    自动在 Agent 的工具列表中注入 generate_bar_chart 等图表生成工具，
    拦截对应的 tool_call 请求，使用 matplotlib 渲染图表后返回图片 URL。
    """

    def get_tools(self):
        return [_make_chart_tool(cd) for cd in ALL_CHARTS]

    async def awrap_model_call(self, request, handler):
        chart_tools = self.get_tools()
        chart_tool_names = {t.name for t in chart_tools}
        extend_tools = [t for t in request.tools if t.name not in chart_tool_names]
        return await handler(request.override(tools=extend_tools + chart_tools))

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        if request.tool_call["name"] not in CHART_MAP:
            return await handler(request)
        cd = CHART_MAP[request.tool_call["name"]]
        try:
            url = render_chart(cd.name, request.tool_call["args"])
            return ToolMessage(
                content=f"![]({url})",
                tool_call_id=request.tool_call["id"],
            )
        except ValidationError as e:
            logger.warning("图表参数验证失败: tool={}, error={}", cd.name, e.errors())
            return ToolMessage(
                content=f"错误: 参数验证失败 - {e.errors()}. 请参考工具描述使用正确的数据格式。",
                tool_call_id=request.tool_call["id"],
            )
        except Exception as e:
            logger.error("图表生成失败: tool={}, error={}", cd.name, repr(e))
            return ToolMessage(
                content=f"错误: 图表生成失败 - {e}.",
                tool_call_id=request.tool_call["id"],
            )
