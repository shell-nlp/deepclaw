from fastapi import APIRouter

from deepclaw.agents.rag.agent import create_rag_agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.common.agui_runs import create_agui_run_router


def create_rag_router(checkpointer=None, store=None) -> APIRouter:
    """创建 RAG API 路由，浏览器运行入口统一使用 AG-UI。

    Args:
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        RAG API 路由器。
    """
    router = APIRouter(prefix="/api/rag")
    agent = create_rag_agent(checkpointer, store)
    router.include_router(
        create_agui_run_router(
            AgentRunManager(agent),
            allowed_state_keys={
                "index_name",
                "graph_name",
                "internet_search",
                "deep_thinking",
            },
            tags=["rag-ag-ui"],
        )
    )
    return router
