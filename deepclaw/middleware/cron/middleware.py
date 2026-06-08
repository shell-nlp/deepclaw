from langchain.agents.middleware import AgentMiddleware

from deepclaw.middleware.cron.cron_tool import cron_tool


class CronMiddleware(AgentMiddleware):
    """注入 cron 工具的中间件。"""

    async def awrap_model_call(self, request, handler):
        has_cron_tool = any(tool.name == cron_tool.name for tool in request.tools)
        if not has_cron_tool:
            request = request.override(tools=[*request.tools, cron_tool])
        return await handler(request)
