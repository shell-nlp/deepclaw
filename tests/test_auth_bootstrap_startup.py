import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from deepclaw.web_backend import app as web_app_module


@asynccontextmanager
async def _noop_channel_lifespan():
    yield


def test_app_lifespan_bootstraps_admin(monkeypatch):
    class ServiceSpy:
        def __init__(self):
            self.calls = 0

        async def bootstrap_admin_if_needed(self):
            self.calls += 1

    service = ServiceSpy()

    async def fake_init_agent_env(app):
        app.state.checkpointer = InMemorySaver()
        app.state.store = InMemoryStore()

    monkeypatch.setattr(web_app_module, "setup_observability", lambda: None)
    monkeypatch.setattr(web_app_module, "patch_langchain", lambda: None)
    monkeypatch.setattr(web_app_module, "init_agent_env", fake_init_agent_env)
    monkeypatch.setattr(web_app_module, "channel_lifespan", _noop_channel_lifespan)
    monkeypatch.setattr(web_app_module, "get_auth_service", lambda: service, raising=False)

    async def run_lifespan():
        async with web_app_module.app_lifespan(web_app_module.FastAPI()):
            pass

    asyncio.run(run_lifespan())

    assert service.calls == 1
