import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI


def test_app_lifespan_bootstraps_admin(monkeypatch):
    from deepclaw import main

    class ServiceSpy:
        def __init__(self):
            self.calls = 0

        def bootstrap_admin_if_needed(self):
            self.calls += 1

    service = ServiceSpy()

    @asynccontextmanager
    async def noop_channel_lifespan():
        yield

    monkeypatch.setattr(main, "setup_observability", lambda: None)
    monkeypatch.setattr(main, "patch_langchain", lambda: None)
    monkeypatch.setattr(main, "channel_lifespan", noop_channel_lifespan)
    monkeypatch.setattr(main, "get_auth_service", lambda: service, raising=False)

    async def run_lifespan():
        async with main.lifespan(FastAPI()):
            pass

    asyncio.run(run_lifespan())

    assert service.calls == 1

