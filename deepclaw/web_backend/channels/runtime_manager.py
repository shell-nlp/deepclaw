import asyncio
from contextlib import suppress
from typing import Any


class ChannelRuntimeManager:
    """统一管理各渠道 runtime task，避免每个 driver 各自维护 task 表。"""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def start(self, runtime_key: str, coroutine) -> asyncio.Task[Any]:
        existing = self._tasks.get(runtime_key)
        if existing is not None and not existing.done():
            close = getattr(coroutine, "close", None)
            if callable(close):
                close()
            return existing

        task = asyncio.create_task(coroutine)
        self._tasks[runtime_key] = task
        return task

    def is_running(self, runtime_key: str) -> bool:
        task = self._tasks.get(runtime_key)
        return task is not None and not task.done()

    async def stop(self, runtime_key: str) -> None:
        task = self._tasks.pop(runtime_key, None)
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def stop_all(self) -> None:
        runtime_keys = list(self._tasks.keys())
        for runtime_key in runtime_keys:
            await self.stop(runtime_key)


_runtime_manager: ChannelRuntimeManager | None = None


def get_channel_runtime_manager() -> ChannelRuntimeManager:
    global _runtime_manager
    if _runtime_manager is None:
        _runtime_manager = ChannelRuntimeManager()
    return _runtime_manager
