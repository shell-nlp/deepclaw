import importlib
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient


def test_importing_app_module_does_not_create_app(monkeypatch):
    import langgraph.checkpoint.memory as checkpoint_memory
    from deepclaw.web_backend import app as app_module

    def fail_on_import(*args, **kwargs):
        raise AssertionError("模块导入阶段不应初始化 InMemorySaver")

    monkeypatch.setattr(checkpoint_memory, "InMemorySaver", fail_on_import)

    importlib.reload(app_module)


def test_app_module_does_not_export_app_instance():
    from deepclaw.web_backend import app as app_module

    with pytest.raises(AttributeError):
        getattr(app_module, "app")


def test_create_app_serves_exported_login_html_route(monkeypatch, tmp_path: Path):
    frontend_out = tmp_path / "frontend" / "out"
    frontend_out.mkdir(parents=True)
    (frontend_out / "index.html").write_text("<html><body>index</body></html>", encoding="utf-8")
    (frontend_out / "login.html").write_text("<html><body>login</body></html>", encoding="utf-8")

    from deepclaw.web_backend import app as app_module

    monkeypatch.setattr(app_module, "root_dir", tmp_path)
    monkeypatch.setattr(app_module, "init_agent_env", lambda: (object(), object()))
    monkeypatch.setattr(app_module, "create_auth_router", lambda: APIRouter())
    monkeypatch.setattr(app_module, "create_agent_router", lambda *args, **kwargs: APIRouter())
    monkeypatch.setattr(app_module, "create_rag_router", lambda *args, **kwargs: APIRouter())
    monkeypatch.setattr(app_module, "create_channels_router", lambda *args, **kwargs: APIRouter())
    monkeypatch.setattr(app_module, "create_skills_router", lambda *args, **kwargs: APIRouter())
    monkeypatch.setattr(
        app_module,
        "create_knowledge_bases_router",
        lambda *args, **kwargs: APIRouter(),
    )

    client = TestClient(app_module.create_app())

    response = client.get("/login")

    assert response.status_code == 200
    assert "login" in response.text
