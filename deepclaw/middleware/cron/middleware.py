from langchain.agents.middleware import AgentMiddleware

from deepclaw.middleware.cron.cron_tool import cron_tool


class CronMiddleware(AgentMiddleware):
    """注入 cron 工具的中间件。"""

    tools = [cron_tool]
