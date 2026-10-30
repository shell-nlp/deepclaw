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


def test_two_managers_share_binding_lease_and_remote_delete_stops_owner(tmp_path, monkeypatch):
    """不同实例只启动一个连接，另一实例删除绑定后持有者退出。

    Args:
        tmp_path: 隔离数据库目录。
        monkeypatch: 缩短绑定状态检查间隔。
    """
    from deepclaw.web_backend.channels import runtime_manager as module
    from deepclaw.web_backend.channels.store import ChannelStore

    monkeypatch.setattr(module, "BINDING_POLL_SECONDS", 0.02)

    async def run():
        """执行租约竞争和远端删除场景。

        Args:
            无。
        """
        stores = [ChannelStore(f"sqlite:///{tmp_path / 'shared.db'}") for _ in range(2)]
        for store in stores:
            await store._ensure_init()
        binding = await stores[0].create_binding(channel="feishu", owner_user_id="u", manager_user_id="u", credentials={})
        managers = [module.ChannelRuntimeManager(), module.ChannelRuntimeManager()]
        starts = []
        started, stopped = asyncio.Event(), asyncio.Event()

        async def factory():
            """模拟持有真实网络连接。

            Args:
                无。
            """
            starts.append(True)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        try:
            for index in range(2):
                await managers[index].start(f"feishu:{binding.id}", factory=factory, store=stores[index])
            await asyncio.wait_for(started.wait(), timeout=3)
            await asyncio.sleep(0.1)
            assert len(starts) == 1
            await stores[1].delete_binding(binding.id)
            await asyncio.wait_for(stopped.wait(), timeout=3)
            assert len(starts) == 1
        finally:
            for manager in managers:
                await manager.stop_all()
            for store in stores:
                await store.engine.dispose()

    asyncio.run(run())
