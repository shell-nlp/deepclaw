from typing import Any

from deepclaw.agent_registry import Agent


class RagAgent(Agent):
    """RAG 智能体。"""

    agent_id = "rag"
    name = "知识库问答"
    description = "基于知识库检索和生成"
    capabilities = frozenset(
        {"knowledge_base", "deep_thinking", "internet_search"}
    )
    allowed_state_keys = frozenset(
        {"index_name", "graph_name", "internet_search", "deep_thinking"}
    )

    @classmethod
    def build_agent(
        cls,
        *,
        checkpointer: Any | None = None,
        store: Any | None = None,
    ) -> Any:
        """构建 RAG Agent 图。

        Args:
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。

        Returns:
            已装配的 RAG Agent 图。
        """
        from langchain.agents import create_agent
        from langchain_deepseek import ChatDeepSeek

        from deepclaw.agents.rag.state import StateSchema
        from deepclaw.middleware.common import BusinessMiddleware
        from deepclaw.middleware.rag import RAGMiddleware
        from deepclaw.settings import settings
        from deepclaw.tools.retriever import get_default_retriever

        model = ChatDeepSeek(
            model=settings.CHAT_MODEL_NAME,
            tags=["agent"],
            api_base=settings.OPENAI_API_BASE,
            api_key=settings.OPENAI_API_KEY,
        )
        rewrite_model = ChatDeepSeek(
            model=settings.CHAT_MODEL_NAME,
            tags=["rag"],
            api_base=settings.OPENAI_API_BASE,
            api_key=settings.OPENAI_API_KEY,
        )
        return create_agent(
            model=model,
            middleware=[
                RAGMiddleware(
                    vector_store=get_default_retriever,
                    rewrite_query=True,
                    model=rewrite_model,
                    retrieve_router=True,
                ),
                BusinessMiddleware(),
            ],
            checkpointer=checkpointer,
            store=store,
            state_schema=StateSchema,
        )
