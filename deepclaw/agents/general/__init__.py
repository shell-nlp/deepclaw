from deepclaw.agents.general.context import AgentContext
from deepclaw.agents.general.state import StateSchema

__all__ = ["GeneralAgent", "AgentContext", "StateSchema"]


def __getattr__(name: str):
    """按需导出通用 Agent 定义，避免状态模块导入时形成循环依赖。

    Args:
        name: 请求的模块属性名。

    Returns:
        通用 Agent 定义类。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "GeneralAgent":
        from deepclaw.agents.general.agent import GeneralAgent

        return GeneralAgent
    raise AttributeError(name)
