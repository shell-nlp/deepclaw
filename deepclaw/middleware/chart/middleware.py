from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from loguru import logger
from pydantic import ValidationError

from deepclaw.middleware.chart.charts import CHART_TYPE_DESCRIPTIONS, ChartSchema
from deepclaw.middleware.chart.engine import render_chart

CHART_SYSTEM_PROMPT = (
    "\n\n## 图表展示规则\n"
    "当你使用 generate_chart 工具生成图表后，工具会返回 Markdown 图片格式的链接。\n"
    "请在你最终的回答中展示这张图片，让用户看到图表内容。\n"
    '不要只说"图表已生成完成"或仅输出工具调用结果而不展示图片。\n'
    "如果有多个图表，请逐一展示。"
)

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
    try:
        url = render_chart(kwargs)
        return f"![]({url})"
    except ValidationError as e:
        logger.warning("图表参数验证失败: error={}", e.errors())
        return f"错误: 参数验证失败 - {e.errors()}. 请参考工具描述使用正确的数据格式。"
    except Exception as e:
        logger.error("图表生成失败: error={}", repr(e))
        return f"错误: 图表生成失败 - {e}."


class ChartMiddleware(AgentMiddleware):
    """图表生成中间件，提供统一 generate_chart 工具给 Agent。"""

    tools = [chart_tool]

    def _override_system_message(self, request):
        if request.system_message is not None:
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": CHART_SYSTEM_PROMPT},
            ]
        else:
            new_system_content = [{"type": "text", "text": CHART_SYSTEM_PROMPT}]

        new_system_message = SystemMessage(content=cast("list[str | dict[str, str]]", new_system_content))
        return new_system_message

    async def awrap_model_call(self, request, handler):
        return await handler(request.override(system_message=self._override_system_message(request)))
