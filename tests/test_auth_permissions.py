from io import BytesIO
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.knowledge_bases.router import (
    router as knowledge_bases_router,
)
from deepclaw.web_backend.skills.router import router as skills_router
from deepclaw.web_backend.skills.service import (
    SkillRecord,
    SkillUploadResponse,
    skill_manager,
)


def build_skill_zip() -> bytes:
    """构造用于测试上传路由的最小技能包。

    Args:
    - 无。
    """
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("demo/SKILL.md", "# demo")
    return buffer.getvalue()


def test_guest_can_upload_skill_but_cannot_create_kb(monkeypatch):
    app = FastAPI()
    app.include_router(skills_router)
    app.include_router(knowledge_bases_router)
    client = TestClient(app, raise_server_exceptions=False)

    captured: dict[str, object] = {}

    def fake_upload_skill_zip(*, file_name: str, data: bytes) -> SkillUploadResponse:
        """记录上传参数并返回稳定的技能上传响应。

        Args:
        - file_name: 上传文件名。
        - data: 上传文件内容。
        """
        captured["file_name"] = file_name
        captured["data"] = data
        return SkillUploadResponse(
            skill=SkillRecord(
                skill_name="demo",
                path="demo",
                description="demo",
                file_count=1,
                created_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:00",
            ),
            extracted_files=1,
        )

    monkeypatch.setattr(skill_manager, "upload_skill_zip", fake_upload_skill_zip)
    skill = client.post(
        "/api/agent/skills/upload",
        files={"file": ("skill.zip", build_skill_zip(), "application/zip")},
    )
    kb = client.post(
        "/api/rag/knowledge-bases/create",
        json={"user_id": "guest", "name": "demo", "description": ""},
    )

    assert skill.status_code == 200
    assert captured["file_name"] == "skill.zip"
    assert isinstance(captured["data"], bytes)
    assert kb.status_code == 403
    assert kb.json()["detail"] == "登录后可创建知识库。"

