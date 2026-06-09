import asyncio


def test_runtime_manager_reuses_existing_running_task():
    from deepclaw.web_backend.channels.runtime_manager import ChannelRuntimeManager

    started = 0

    async def runner():
        nonlocal started
        started += 1
        await asyncio.Event().wait()

    async def main():
        manager = ChannelRuntimeManager()
        first = await manager.start("feishu:1", runner())
        second = await manager.start("feishu:1", runner())
        await asyncio.sleep(0)
        assert first is second
        assert manager.is_running("feishu:1") is True
        assert started == 1
        await manager.stop("feishu:1")
        assert manager.is_running("feishu:1") is False

    asyncio.run(main())


def test_runtime_manager_stop_all_cancels_tasks():
    from deepclaw.web_backend.channels.runtime_manager import ChannelRuntimeManager

    cancelled: list[str] = []

    async def runner(name: str):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(name)
            raise

    async def main():
        manager = ChannelRuntimeManager()
        await manager.start("weixin:1", runner("weixin:1"))
        await manager.start("feishu:2", runner("feishu:2"))
        await asyncio.sleep(0)
        await manager.stop_all()

    asyncio.run(main())

    assert sorted(cancelled) == ["feishu:2", "weixin:1"]
