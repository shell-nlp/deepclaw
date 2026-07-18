from fastapi import APIRouter

from deepclaw.agents.rag.agent import create_rag_agent
from deepclaw.agents.rag.context import AgentContext
from deepclaw.web_backend.common.endpoints import (
    add_general_api_endpoint as add_general_api_endpoint_v1,
)
from deepclaw.web_backend.common.endpoints_v2 import (
    add_general_api_endpoint as add_general_api_endpoint_v2,
)


def create_rag_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/rag")
    general_api_router = APIRouter()
    rag_agent = create_rag_agent(checkpointer, store)
    # v1：astream messages/updates
    add_general_api_endpoint_v1(
        app=general_api_router,
        agent=rag_agent,
        path="/general_api",
        context=AgentContext,
        name="rag_general_api",
        tags=["rag-chat"],
    )
    # v2：astream_events v3，便于对照测试
    add_general_api_endpoint_v2(
        app=general_api_router,
        agent=rag_agent,
        path="/v2/general_api",
        context=AgentContext,
        name="rag_general_api_v2",
        tags=["rag-chat-v2"],
    )
    router.include_router(general_api_router)
    return router


