from langchain.agents.middleware import AgentMiddleware

from deepclaw.middleware.python_executor.tool import python_executor


class PythonExecutorMiddleware(AgentMiddleware):
    """在 Agent 的模型调用中自动注入 python_executor 工具。"""

    tools = [python_executor]
