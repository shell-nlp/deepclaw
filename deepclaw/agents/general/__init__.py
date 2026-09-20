from deepclaw.agents.general.context import AgentContext
from deepclaw.agents.general.state import StateSchema

__all__ = ["Agent", "AgentContext", "StateSchema"]


def __getattr__(name: str):
    """按需导出通用 Agent，避免状态模块导入时形成循环依赖。

    Args:
        name: 请求的模块属性名。

    Returns:
        通用 Agent 类。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "Agent":
        from deepclaw.agents.general.agent import Agent

        return Agent
    raise AttributeError(name)
