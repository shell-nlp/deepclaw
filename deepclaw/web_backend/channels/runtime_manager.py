import asyncio
from contextlib import suppress
from typing import Any

from loguru import logger

from deepclaw.web_backend.channels.jobs import ChannelJobStore

BINDING_POLL_SECONDS = 5


class ChannelRuntimeManager:
    """统一管理各渠道 runtime task，避免每个 driver 各自维护 task 表。"""

    def __init__(self):
        """初始化本进程的运行任务表。

        Args:
            无。
        """
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def start(self, runtime_key: str, coroutine=None, *, factory=None, store=None) -> asyncio.Task[Any]:
        """启动唯一任务，可选绑定租约和失败退避重启。

        Args:
            runtime_key: 渠道绑定运行标识。
            coroutine: 无需重启的单次协程。
            factory: 每次启动时创建新协程的工厂。
            store: 使用共享数据库租约的渠道存储。
        """
        existing = self._tasks.get(runtime_key)
        if existing is not None and not existing.done():
            close = getattr(coroutine, "close", None)
            if callable(close):
                close()
            return existing

        task = asyncio.create_task(self._supervise(runtime_key, factory, store) if factory else coroutine)
        self._tasks[runtime_key] = task
        return task

    async def _supervise(self, runtime_key, factory, store):
        """租约保护绑定运行，异常退出后指数退避。

        Args:
            runtime_key: 绑定运行标识。
            factory: 协程工厂。
            store: 共享存储。
        """
        attempts = 0
        while True:
            try:
                binding_id = self._binding_id(runtime_key)
                if store is not None and binding_id is not None:
                    binding = await store.get_binding(binding_id)
                    if binding is None or binding.status != "active":
                        return
                if store is None:
                    await factory()
                else:
                    async with ChannelJobStore(store).lease(f"runtime:{runtime_key}") as acquired:
                        if acquired:
                            await self._run_owned(runtime_key, factory, store)
                attempts = min(attempts + 1, 6)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempts = min(attempts + 1, 6)
                logger.exception("渠道运行时退出，将重新连接：{}", runtime_key)
            await asyncio.sleep(min(2 ** attempts, 60))

    def _binding_id(self, runtime_key):
        """从绑定运行键提取绑定 ID，历史状态运行键返回空。

        Args:
            runtime_key: 渠道运行键。
        """
        if runtime_key.startswith(("feishu:", "weixin:binding:")):
            return int(runtime_key.rsplit(":", 1)[1])
        return None

    async def _run_owned(self, runtime_key, factory, store):
        """持有租约期间监听绑定删除或停用，跨实例及时停止连接。

        Args:
            runtime_key: 渠道运行键。
            factory: 运行协程工厂。
            store: 共享数据库存储。
        """
        binding_id = self._binding_id(runtime_key)
        if binding_id is None:
            await factory()
            return

        async def watch():
            """监听绑定状态，不依赖删除请求发生在哪个进程。

            Args:
                无。
            """
            while True:
                await asyncio.sleep(BINDING_POLL_SECONDS)
                binding = await store.get_binding(binding_id)
                if binding is None or binding.status != "active":
                    return

        runner, watcher = asyncio.create_task(factory()), asyncio.create_task(watch())
        try:
            done, _ = await asyncio.wait([runner, watcher], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        finally:
            runner.cancel()
            watcher.cancel()
            await asyncio.gather(runner, watcher, return_exceptions=True)

    def is_running(self, runtime_key: str) -> bool:
        """查询本进程是否仍在监管任务。

        Args:
            runtime_key: 运行标识。
        """
        task = self._tasks.get(runtime_key)
        return task is not None and not task.done()

    async def stop(self, runtime_key: str) -> None:
        """取消任务并等待运行资源释放。

        Args:
            runtime_key: 运行标识。
        """
        task = self._tasks.pop(runtime_key, None)
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def stop_all(self) -> None:
        """停止全部渠道任务，即使个别任务清理失败也继续清理。

        Args:
            无。
        """
        runtime_keys = list(self._tasks.keys())
        for runtime_key in runtime_keys:
            with suppress(Exception):
                await self.stop(runtime_key)

    async def stop_prefix(self, prefix: str) -> None:
        """停止指定渠道的运行任务。

        Args:
            prefix: 渠道运行键前缀。
        """
        for key in list(self._tasks):
            if key.startswith(prefix):
                with suppress(Exception):
                    await self.stop(key)


_runtime_manager: ChannelRuntimeManager | None = None


def get_channel_runtime_manager() -> ChannelRuntimeManager:
    """获取进程内统一运行时管理器。

    Args:
        无。
    """
    global _runtime_manager
    if _runtime_manager is None:
        _runtime_manager = ChannelRuntimeManager()
    return _runtime_manager
