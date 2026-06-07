from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek

from deepclaw.middleware.common import BusinessMiddleware
from deepclaw.middleware.rag import RAGMiddleware
from deepclaw.settings import settings
from deepclaw.tools.retriever import es_retriever


def create_rag_agent(checkpointer=None, store=None):
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
                es=es_retriever,
                rewrite_query=True,
                model=rewrite_model,
                retrieve_router=True,
            ),
            BusinessMiddleware(),
        ],
        checkpointer=checkpointer,
        store=store,
    )

