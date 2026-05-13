from fastapi import APIRouter

from langchain_api.api.endpoints import add_general_api_endpoint
from langchain_api.api.management.knowledge_bases import (
    add_knowledge_base_management_routes,
)
from langchain_api.rag.agent import create_rag_agent
from langchain_api.rag.context import AgentContext


def create_rag_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/rag")
    general_api_router = APIRouter()
    management_router = APIRouter()
    add_knowledge_base_management_routes(
        management_router, tags=["rag-knowledge-bases"]
    )
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
    router.include_router(management_router)
    return router
