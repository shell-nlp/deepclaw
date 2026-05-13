from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import APIRouter

from langchain_api.agent.agent import Agent
from langchain_api.agent.context import AgentContext
from langchain_api.api.endpoints import add_general_api_endpoint
from langchain_api.api.management.skills import add_skill_management_routes


def create_agent_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/agent")
    ag_ui_router = APIRouter(tags=["agent-ag-ui"])
    general_api_router = APIRouter()
    management_router = APIRouter()
    agent = Agent(deep_agent=True, checkpointer=checkpointer, store=store).get_agent()
    add_skill_management_routes(management_router, tags=["agent-skills"])

    add_langgraph_fastapi_endpoint(
        app=ag_ui_router,
        agent=LangGraphAGUIAgent(
            name="agent",
            description="DeepAgent service.",
            graph=agent,
        ),
        path="/ag_ui",
    )

    add_general_api_endpoint(
        app=general_api_router,
        agent=agent,
        path="/general_api",
        context=AgentContext,
        name="agent_general_api",
        tags=["agent-chat"],
    )

    router.include_router(ag_ui_router)
    router.include_router(general_api_router)
    router.include_router(management_router)

    return router
