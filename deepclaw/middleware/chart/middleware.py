from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from loguru import logger
from pydantic import ValidationError

from deepclaw.middleware.chart.engine import render_chart
from deepclaw.middleware.chart.schemas import CHART_TYPE_DESCRIPTIONS, ChartSchema

CHART_PROMPT_MARKER = "## 图表工具使用规范"

CHART_SYSTEM_PROMPT = (
    f"\n\n{CHART_PROMPT_MARKER}\n"
    "仅在用户已提供数据、或当前上下文中存在可信的结构化数据且可视化能帮助理解时，才调用 generate_chart；"
    "不得为了生成图表而编造、补全或猜测数据。数据不足时，先向用户索取必要数据。\n"
    "图表选型：时间趋势用 line/area；类别比较用 bar/column；占比用 pie；数据分布用 histogram；"
    "转化流程用 funnel；两个数值变量的关系用 scatter；多维指标对比用 radar。\n"
    "调用前必须核对字段：bar/column/pie 使用 category、value；line/area 使用 time、value；"
    "scatter 使用 x、y；radar 使用 item、score；funnel 使用 stage、value；histogram 使用纯数值或 value。"
    "分组时每条数据都必须有 group，且同一维度与 group 的组合不能重复。pie/funnel 的 value 必须非负且至少一个为正数。"
    "调用工具时必须传入原始数值，不得调整数值量级；图表直接使用原始数值绘制，不做万、百万或亿换算。"
    "数值过长时使用正确的科学计数法表示。"
    "stack 仅可用于 bar/column；bar 分组同时包含数量和比例类指标时，工具会使用双横轴分别展示。"
    "bar 会按数值降序展示。"
    "图表应包含清晰 title；有坐标轴时应尽量补充 axisXTitle、axisYTitle 和单位。\n"
    "如果工具返回参数错误，先依据错误信息修正参数并重试一次；仍无法生成时，说明缺少或不合法的数据，不得声称图表已生成。\n"
    "工具成功时会返回 Markdown 图片。最终回答必须原样保留并展示该 Markdown 图片，使用户在回答中直接看到图表；"
    '不能只回复“图片已生成”或“图表已完成”。图片后应给出简短的数据解读或关键结论。'
    "有多个图表时逐一展示，并分别说明结论。"
)

CHART_TOOL_DESCRIPTION = (
    "生成统计图表（9 种类型可用）。根据 chart_type 选择图表类型，传入对应格式的数据。\n\n"
    + "图表类型说明:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CHART_TYPE_DESCRIPTIONS.items())
    + "\n\n数据格式:\n"
    + "- bar/column/pie: [{'category': 'A', 'value': 10, 'group': '组别'}, ...]\n"
    + "- line/area: [{'time': '2020', 'value': 10, 'group': '组别'}, ...]\n"
    + "- scatter: [{'x': 1, 'y': 2, 'group': '组别'}, ...]\n"
    + "- radar: [{'item': '速度', 'score': 80, 'group': '组别'}, ...]\n"
    + "- funnel: [{'stage': '访问', 'value': 100}, ...]\n"
    + "- histogram: [1, 2, 3] 或 [{'value': 1}, ...]"
    + "\n\n使用规则:\n"
    + "- 仅使用用户提供或上下文中可信的数据，不得编造数据。\n"
    + "- 分组时每条数据都提供 group，且同一维度与 group 的组合不能重复。\n"
    + "- pie/funnel 的 value 必须非负且至少有一个正数；stack 仅用于 bar/column。\n"
    + "- bar 分组同时包含数量和比例类指标时，工具会自动使用双横轴展示。\n"
    + "- 必须传入原始数值，不得调整数值量级；工具不做万、百万或亿换算，过长数值使用科学计数法。\n"
    + "- 请提供清晰 title；有坐标轴时补充 axisXTitle、axisYTitle 和单位。"
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
        """向系统消息注入一次图表工具使用规范。

        Args:
            request: LangChain 当前模型调用请求。

        Returns:
            SystemMessage: 包含图表工具规范的系统消息。
        """
        if request.system_message is not None:
            if any(CHART_PROMPT_MARKER in str(block) for block in request.system_message.content_blocks):
                return request.system_message
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": CHART_SYSTEM_PROMPT},
            ]
        else:
            new_system_content = [{"type": "text", "text": CHART_SYSTEM_PROMPT}]

        new_system_message = SystemMessage(content=cast("list[str | dict[str, str]]", new_system_content))
        return new_system_message

    async def awrap_model_call(self, request, handler):
        """在模型调用前注入图表工具规范。

        Args:
            request: LangChain 当前模型调用请求。
            handler: 后续模型调用处理器。

        Returns:
            Any: 后续处理器返回的模型调用结果。
        """
        return await handler(request.override(system_message=self._override_system_message(request)))
