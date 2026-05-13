from fastapi import APIRouter

from langchain_api.api.endpoints import add_general_api_endpoint
from langchain_api.api.management.knowledge_bases import (
    add_knowledge_base_management_routes,
)
from langchain_api.rag.agent import create_rag_agent
from langchain_api.rag.context import AgentContext


def create_rag_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/rag")
    add_knowledge_base_management_routes(router)
    rag_agent = create_rag_agent(checkpointer, store)
    add_general_api_endpoint(
        app=router,
        agent=rag_agent,
        path="/general_api",
        context=AgentContext,
        name="rag_general_api",
    )
    return router
