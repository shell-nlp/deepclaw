from fastapi import APIRouter, FastAPI

from langchain_api.api import add_general_api_endpoint
from langchain_api.rag.context import AgentContext


def add_rag_api_endpoint(
    app: FastAPI | APIRouter,
    agent,
    path: str = "/api/rag/general_api",
):
    add_general_api_endpoint(
        app=app,
        agent=agent,
        path=path,
        context=AgentContext,
        name="rag_general_api",
    )
