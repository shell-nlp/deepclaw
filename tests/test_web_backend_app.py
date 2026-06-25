import importlib
import asyncio
import sys
import types
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient


def _load_app_module(monkeypatch):
    router_modules = {
        "deepclaw.web_backend.agent.router": "create_agent_router",
        "deepclaw.web_backend.auth.router": "create_auth_router",
        "deepclaw.web_backend.channels.router": "create_channels_router",
        "deepclaw.web_backend.knowledge_bases.router": "create_knowledge_bases_router",
        "deepclaw.web_backend.rag.router": "create_rag_router",
        "deepclaw.web_backend.skills.router": "create_skills_router",
    }

    for module_name, factory_name in router_modules.items():
        module = types.ModuleType(module_name)

        def _build_router(*args, **kwargs):
            return APIRouter()

        setattr(module, factory_name, _build_router)
        monkeypatch.setitem(sys.modules, module_name, module)

    from deepclaw.web_backend import app as app_module

    return importlib.reload(app_module)


def test_importing_app_module_does_not_create_app(monkeypatch):
    import langgraph.checkpoint.memory as checkpoint_memory

    def fail_on_import(*args, **kwargs):
        raise AssertionError("模块导入阶段不应初始化 InMemorySaver")

    monkeypatch.setattr(checkpoint_memory, "InMemorySaver", fail_on_import)

    _load_app_module(monkeypatch)


def test_app_module_does_not_export_app_instance(monkeypatch):
    app_module = _load_app_module(monkeypatch)

    with pytest.raises(AttributeError):
        getattr(app_module, "app")


def test_create_app_defers_agent_env_init_to_lifespan(monkeypatch):
    from contextlib import asynccontextmanager

    app_module = _load_app_module(monkeypatch)

    checkpointer = object()
    store = object()
    init_calls = 0
    agent_router_args = []
    rag_router_args = []

    async def fake_init_agent_env(app):
        nonlocal init_calls
        init_calls += 1
        app.state.checkpointer = checkpointer
        app.state.store = store

    def fake_create_agent_router(*args, **kwargs):
        agent_router_args.append((args, kwargs))
        return APIRouter()

    def fake_create_rag_router(*args, **kwargs):
        rag_router_args.append((args, kwargs))
        return APIRouter()

    class ServiceSpy:
        async def bootstrap_admin_if_needed(self):
            return None

    @asynccontextmanager
    async def noop_channel_lifespan():
        yield

    monkeypatch.setattr(app_module, "init_agent_env", fake_init_agent_env)
    monkeypatch.setattr(app_module, "create_auth_router", lambda: APIRouter())
    monkeypatch.setattr(app_module, "create_agent_router", fake_create_agent_router)
    monkeypatch.setattr(app_module, "create_rag_router", fake_create_rag_router)
    monkeypatch.setattr(app_module, "create_channels_router", lambda: APIRouter())
    monkeypatch.setattr(app_module, "create_skills_router", lambda: APIRouter())
    monkeypatch.setattr(
        app_module,
        "create_knowledge_bases_router",
        lambda *args, **kwargs: APIRouter(),
    )
    monkeypatch.setattr(app_module, "setup_observability", lambda: None)
    monkeypatch.setattr(app_module, "patch_langchain", lambda: None)
    monkeypatch.setattr(app_module, "channel_lifespan", noop_channel_lifespan)
    monkeypatch.setattr(app_module, "get_auth_service", lambda: ServiceSpy())

    app = app_module.create_app()

    assert init_calls == 0
    assert agent_router_args == []
    assert rag_router_args == []

    with TestClient(app):
        pass

    assert init_calls == 1
    assert agent_router_args == [((checkpointer, store), {})]
    assert rag_router_args == [((checkpointer, store), {})]


def test_init_agent_env_keeps_postgres_checkpointer_context_alive(monkeypatch):
    app_module = _load_app_module(monkeypatch)

    class FakeCheckpointer:
        def __init__(self):
            self.setup_calls = 0

        async def setup(self):
            self.setup_calls += 1

    class FakeAsyncCheckpointerCtx:
        def __init__(self, checkpointer):
            self.checkpointer = checkpointer
            self.entered = False

        async def __aenter__(self):
            self.entered = True
            return self.checkpointer

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeStore:
        def __init__(self):
            self.setup_calls = 0

        def setup(self):
            self.setup_calls += 1

    class FakeStoreCtx:
        def __init__(self, store):
            self.store = store

        def __enter__(self):
            return self.store

        def __exit__(self, exc_type, exc, tb):
            return None

    checkpointer = FakeCheckpointer()
    checkpointer_ctx = FakeAsyncCheckpointerCtx(checkpointer)
    store = FakeStore()
    store_ctx = FakeStoreCtx(store)

    checkpoint_module = types.ModuleType("langgraph.checkpoint.postgres.aio")
    checkpoint_module.AsyncPostgresSaver = types.SimpleNamespace(
        from_conn_string=lambda *args, **kwargs: checkpointer_ctx
    )
    store_module = types.ModuleType("langgraph.store.postgres")
    store_module.PostgresStore = types.SimpleNamespace(
        from_conn_string=lambda *args, **kwargs: store_ctx
    )

    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres.aio", checkpoint_module)
    monkeypatch.setitem(sys.modules, "langgraph.store.postgres", store_module)
    monkeypatch.setattr(app_module.settings, "PG_DATABASE_URL", "postgresql://example")

    app = app_module.FastAPI()

    asyncio.run(app_module.init_agent_env(app))

    assert app.state.checkpointer is checkpointer
    assert app.state.agent_checkpointer_ctx is checkpointer_ctx
    assert app.state.store is store
    assert app.state.agent_store_ctx is store_ctx
    assert checkpointer.setup_calls == 1
    assert store.setup_calls == 1


def test_create_app_agent_route_remains_postable_with_frontend_mount(monkeypatch, tmp_path: Path):
    from contextlib import asynccontextmanager

    app_module = _load_app_module(monkeypatch)
    frontend_out = tmp_path / "frontend" / "out"
    frontend_out.mkdir(parents=True)
    (frontend_out / "index.html").write_text("<html><body>index</body></html>", encoding="utf-8")

    async def fake_init_agent_env(app):
        app.state.checkpointer = object()
        app.state.store = object()
        app.state.agent_store_ctx = None

    def fake_create_agent_router(*args, **kwargs):
        router = APIRouter()

        @router.post("/api/agent/general_api")
        async def general_api():
            return {"ok": True}

        return router

    class ServiceSpy:
        async def bootstrap_admin_if_needed(self):
            return None

    @asynccontextmanager
    async def noop_channel_lifespan():
        yield

    monkeypatch.setattr(app_module, "root_dir", tmp_path)
    monkeypatch.setattr(app_module, "init_agent_env", fake_init_agent_env)
    monkeypatch.setattr(app_module, "create_auth_router", lambda: APIRouter())
    monkeypatch.setattr(app_module, "create_agent_router", fake_create_agent_router)
    monkeypatch.setattr(app_module, "create_rag_router", lambda *args, **kwargs: APIRouter())
    monkeypatch.setattr(app_module, "create_channels_router", lambda: APIRouter())
    monkeypatch.setattr(app_module, "create_skills_router", lambda: APIRouter())
    monkeypatch.setattr(
        app_module,
        "create_knowledge_bases_router",
        lambda *args, **kwargs: APIRouter(),
    )
    monkeypatch.setattr(app_module, "setup_observability", lambda: None)
    monkeypatch.setattr(app_module, "patch_langchain", lambda: None)
    monkeypatch.setattr(app_module, "channel_lifespan", noop_channel_lifespan)
    monkeypatch.setattr(app_module, "get_auth_service", lambda: ServiceSpy())

    with TestClient(app_module.create_app()) as client:
        response = client.post("/api/agent/general_api", json={"query": "你好"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_create_app_serves_exported_login_html_route(monkeypatch, tmp_path: Path):
    frontend_out = tmp_path / "frontend" / "out"
    frontend_out.mkdir(parents=True)
    (frontend_out / "index.html").write_text("<html><body>index</body></html>", encoding="utf-8")
    (frontend_out / "login.html").write_text("<html><body>login</body></html>", encoding="utf-8")

    from contextlib import asynccontextmanager

    app_module = _load_app_module(monkeypatch)

    monkeypatch.setattr(app_module, "root_dir", tmp_path)
    async def fake_init_agent_env(app):
        app.state.checkpointer = object()
        app.state.store = object()
        app.state.agent_store_ctx = None

    class ServiceSpy:
        async def bootstrap_admin_if_needed(self):
            return None

    @asynccontextmanager
    async def noop_channel_lifespan():
        yield

    monkeypatch.setattr(app_module, "init_agent_env", fake_init_agent_env)
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
    monkeypatch.setattr(app_module, "setup_observability", lambda: None)
    monkeypatch.setattr(app_module, "patch_langchain", lambda: None)
    monkeypatch.setattr(app_module, "channel_lifespan", noop_channel_lifespan)
    monkeypatch.setattr(app_module, "get_auth_service", lambda: ServiceSpy())

    with TestClient(app_module.create_app()) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert "login" in response.text
