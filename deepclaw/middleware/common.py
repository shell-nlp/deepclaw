import os
from typing import cast

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import SystemMessage, ToolMessage
from loguru import logger

from deepclaw.agents.general.context import AgentContext
from deepclaw.agents.general.state import StateSchema
from deepclaw.utils import get_current_time


# https://github.com/CopilotKit/CopilotKit/issues/2646
class BusinessMiddleware(AgentMiddleware[None, AgentContext, None]):
    """业务中间件，用于处理业务相关的逻辑"""

    state_schema = StateSchema

    def __init__(self) -> None:
        self.tools = []
        if os.getenv("TAVILY_API_KEY"):
            logger.info("TAVILY_API_KEY 已配置，将添加 TavilySearch 工具")
            from langchain_tavily.tavily_search import TavilySearch

            self.tools.append(TavilySearch())

    def _override_system_message(self, request):

        current_time = get_current_time()
        prompt_suffix = f"## 系统时间{current_time}"
        if request.system_message is not None:
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": f"\n\n{prompt_suffix}"},
            ]
        else:
            new_system_content = [{"type": "text", "text": prompt_suffix}]

        new_system_message = SystemMessage(content=cast("list[str | dict[str, str]]", new_system_content))
        return new_system_message

    def wrap_model_call(self, request, handler):
        context: AgentContext = request.runtime.context
        internet_search = context.internet_search
        deep_thinking = context.deep_thinking
        if not internet_search:
            # 禁用互联网搜索相关的工具调用
            filtered_tools = [tool for tool in request.tools if tool.name != "tavily_search"]
            request = request.override(tools=filtered_tools)

        # 处理深度思考
        if hasattr(request, "model_settings"):
            model_settings = request.model_settings.copy()
        else:
            model_settings = {}
        if deep_thinking:
            # 为模型调用添加深度思考参数
            model_settings["extra_body"] = model_settings.get("extra_body", {})
            model_settings["extra_body"]["chat_template_kwargs"] = {"enable_thinking": True}
            model_settings["extra_body"]["thinking"] = {"type": "enabled"}
            request = request.override(model_settings=model_settings)
        else:
            # 移除深度思考参数
            model_settings["extra_body"] = model_settings.get("extra_body", {})
            model_settings["extra_body"]["chat_template_kwargs"] = {"enable_thinking": False}
            model_settings["extra_body"]["thinking"] = {"type": "disabled"}
            request = request.override(model_settings=model_settings)
        return handler(request.override(system_message=self._override_system_message(request)))

    async def awrap_model_call(self, request, handler):
        return await self.wrap_model_call(request, handler)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        """将工具执行异常转换为可供模型修正参数的错误消息。

        Args:
            request: 当前工具调用请求。
            handler: 执行实际工具调用的异步处理器。

        Returns:
            正常工具结果，或携带原工具调用标识的错误 ToolMessage。
        """
        try:
            return await handler(request)
        except Exception as exc:
            tool_call = request.tool_call
            tool_name = tool_call.get("name", "未知工具")
            logger.warning("工具执行失败，已返回给模型修正: {}: {}", tool_name, exc)
            return ToolMessage(
                content=f"工具 {tool_name} 执行失败：{exc}",
                tool_call_id=tool_call["id"],
                status="error",
            )
