from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from langchain_api.api.agent.api.skills import add_skill_management_routes
from langchain_api.api.rag.api.knowledge_bases import (
    add_knowledge_base_management_routes,
)


def test_guest_cannot_upload_skill_or_create_kb():
    app = FastAPI()
    router = APIRouter()
    add_skill_management_routes(router, tags=["agent-skills"])
    add_knowledge_base_management_routes(router, tags=["rag-knowledge-bases"])
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    skill = client.post(
        "/skills/upload",
        files={"file": ("skill.zip", b"fake", "application/zip")},
    )
    kb = client.post(
        "/knowledge-bases/create",
        json={"user_id": "guest", "name": "demo", "description": ""},
    )

    assert skill.status_code == 403
    assert skill.json()["detail"] == "登录后可上传技能。"
    assert kb.status_code == 403
    assert kb.json()["detail"] == "登录后可创建知识库。"
