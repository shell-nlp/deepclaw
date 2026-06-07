from fastapi import APIRouter

from langchain_api.agents.rag.agent import create_rag_agent
from langchain_api.agents.rag.context import AgentContext
from langchain_api.web_backend.common.endpoints import add_general_api_endpoint


def create_rag_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/rag")
    general_api_router = APIRouter()
    rag_agent = create_rag_agent(checkpointer, store)
    add_general_api_endpoint(
        app=general_api_router,
        agent=rag_agent,
        path="/general_api",
        context=AgentContext,
        name="rag_general_api",
        tags=["rag-chat"],
    )
    router.include_router(general_api_router)
    return router

