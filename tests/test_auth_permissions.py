from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.knowledge_bases.router import (
    router as knowledge_bases_router,
)
from deepclaw.web_backend.skills.router import router as skills_router


def test_guest_cannot_upload_skill_or_create_kb():
    app = FastAPI()
    app.include_router(skills_router)
    app.include_router(knowledge_bases_router)
    client = TestClient(app, raise_server_exceptions=False)

    skill = client.post(
        "/api/agent/skills/upload",
        files={"file": ("skill.zip", b"fake", "application/zip")},
    )
    kb = client.post(
        "/api/rag/knowledge-bases/create",
        json={"user_id": "guest", "name": "demo", "description": ""},
    )

    assert skill.status_code == 403
    assert skill.json()["detail"] == "登录后可上传技能。"
    assert kb.status_code == 403
    assert kb.json()["detail"] == "登录后可创建知识库。"

