from deepclaw.agents.rag.context import AgentContext
from deepclaw.agents.rag.state import StateSchema

__all__ = ["create_rag_agent", "AgentContext", "StateSchema"]


def __getattr__(name: str):
    """按需导出 RAG Agent，避免状态模块导入时形成循环依赖。

    Args:
        name: 请求的模块属性名。

    Returns:
        RAG Agent 创建函数。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "create_rag_agent":
        from deepclaw.agents.rag.agent import create_rag_agent

        return create_rag_agent
    raise AttributeError(name)
