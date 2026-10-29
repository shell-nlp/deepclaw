import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from deepclaw.web_backend import lifespan as lifespan_module


@asynccontextmanager
async def _noop_channel_lifespan():
    yield


class UploadManagerSpy:
    """避免启动测试连接真实知识库存储。"""

    async def start_upload_workers(self):
        """模拟启动上传 worker。

        Args:
            无。
        """

    async def stop_upload_workers(self):
        """模拟停止上传 worker。

        Args:
            无。
        """


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

    async def noop_preload(self, **kwargs):
        """跳过智能体预热。

        Args:
            self: 运行时缓存实例。
            **kwargs: 预热参数。
        """
        return None

    monkeypatch.setattr(lifespan_module, "validate_runtime_settings", lambda: None)
    monkeypatch.setattr(lifespan_module, "setup_observability", lambda: None)
    monkeypatch.setattr(lifespan_module, "init_agent_env", fake_init_agent_env)
    monkeypatch.setattr(lifespan_module, "channel_lifespan", _noop_channel_lifespan)
    monkeypatch.setattr(lifespan_module, "get_auth_service", lambda: service)
    monkeypatch.setattr(
        lifespan_module,
        "get_knowledge_base_manager",
        lambda: UploadManagerSpy(),
    )
    monkeypatch.setattr(
        lifespan_module.AgentRuntimeCache,
        "preload",
        noop_preload,
    )

    async def run_lifespan():
        async with lifespan_module.app_lifespan(lifespan_module.FastAPI()):
            pass

    asyncio.run(run_lifespan())

    assert service.calls == 1
