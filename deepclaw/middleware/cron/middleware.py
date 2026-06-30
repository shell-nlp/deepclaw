from langchain.agents.middleware import AgentMiddleware

from deepclaw.middleware.cron.cron_tool import cron_tool


class CronMiddleware(AgentMiddleware):
    """注入 cron 工具的中间件。"""

    tools = [cron_tool]

    def wrap_model_call(self, request, handler):
        """在请求的 tools 列表中追加 cron 工具。"""
        existing_tools = getattr(request, "tools", []) or []
        updated_tools = existing_tools + self.tools
        return handler(request.override(tools=updated_tools))

    async def awrap_model_call(self, request, handler):
        return await self.wrap_model_call(request, handler)
