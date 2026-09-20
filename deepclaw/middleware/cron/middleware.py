from langchain.agents.middleware import AgentMiddleware

from deepclaw.middleware.cron.cron_tool import cron_tool


class CronMiddleware(AgentMiddleware):
    """注入 cron 工具的中间件。"""

    tools = [cron_tool]

    def wrap_model_call(self, request, handler):
        """在请求的 tools 列表中追加尚未存在的 cron 工具。

        Args:
            request: 当前模型调用请求。
            handler: 后续模型调用处理器。

        Returns:
            处理后的模型调用结果。
        """
        existing_tools = getattr(request, "tools", []) or []
        existing_names = {tool.name for tool in existing_tools}
        updated_tools = list(existing_tools)
        for tool in self.tools:
            if tool.name in existing_names:
                continue
            updated_tools.append(tool)
            existing_names.add(tool.name)
        return handler(request.override(tools=updated_tools))

    async def awrap_model_call(self, request, handler):
        return await self.wrap_model_call(request, handler)
