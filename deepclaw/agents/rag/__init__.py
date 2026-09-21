from deepclaw.agents.rag.context import AgentContext
from deepclaw.agents.rag.state import StateSchema

__all__ = ["RagAgent", "AgentContext", "StateSchema"]


def __getattr__(name: str):
    """按需导出 RAG Agent 定义，避免状态模块导入时形成循环依赖。

    Args:
        name: 请求的模块属性名。

    Returns:
        RAG Agent 定义类。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "RagAgent":
        from deepclaw.agents.rag.agent import RagAgent

        return RagAgent
    raise AttributeError(name)
