import asyncio
from contextlib import suppress
from typing import Any

from loguru import logger

from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway
from deepclaw.web_backend.channels.feishu.settings import feishu_settings
from deepclaw.web_backend.channels.feishu.connection import run_connection, normalize_event
from deepclaw.web_backend.channels.models import ChannelBinding
from deepclaw.web_backend.channels.runtime_manager import get_channel_runtime_manager
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


class FeishuRuntime:
    """单个 binding 对应一个飞书长连接 runtime。"""

    def __init__(
        self,
        *,
        binding: ChannelBinding,
        service: ChannelService | None = None,
        store: ChannelStore | None = None,
        gateway: FeishuClientGateway | None = None,
    ):
        self.binding = binding
        self.service = service or ChannelService(store=store)
        self.store = store
        self.gateway = gateway or FeishuClientGateway()
        self.adapter = FeishuAdapter(binding=binding, gateway=self.gateway)
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = asyncio.Event()
        self._message_tasks: set[asyncio.Task] = set()
        self._bot_open_id: str | None = None

    def should_process_event(self, event: dict[str, Any]) -> bool:
        chat_type = str(event.get("chat_type") or "group")
        if chat_type == "p2p":
            return True
        group_policy = str(self.binding.config.get("group_policy") or feishu_settings.FEISHU_DEFAULT_GROUP_POLICY)
        if group_policy == "open":
            return True
        mentions = event.get("mentions") or []
        if not mentions:
            return False
        if not self._bot_open_id:
            return True
        return any(self._mention_matches_current_bot(mention) for mention in mentions)

    async def handle_event(self, event: dict[str, Any]) -> None:
        if not self.should_process_event(event):
            return
        message = await self.adapter.parse_event(event)
        message.user_id = self.binding.owner_user_id
        message.manager_user_id = self.binding.manager_user_id
        await self.service.process_message(message, self.adapter)

    async def run_forever(self) -> None:
        """运行独立连接进程并同步真实连接状态。

        Args:
            无。
        """
        self._running = True
        self._stop_event = asyncio.Event()
        await self._sync_binding_state(runtime_state={"status": "starting"})
        connection_task = None
        stop_task = None
        failed = False
        try:
            if self.store is not None and self.binding.id is not None:
                latest = await self.store.get_binding(self.binding.id)
                if latest is None:
                    return
                self.binding = latest
                self.adapter.binding = latest
            self._bot_open_id = await self.gateway.fetch_bot_open_id(binding=self.binding)
            runner = getattr(self.gateway, "run_connection", run_connection)
            connection_task = asyncio.create_task(runner(self.binding, self._accept_event, self._connection_status))
            stop_task = asyncio.create_task(self._stop_event.wait())
            done, _ = await asyncio.wait([connection_task, stop_task], return_when=asyncio.FIRST_COMPLETED)
            if connection_task in done:
                await connection_task
                raise ConnectionError("飞书连接已退出")
        except asyncio.CancelledError:
            raise
        except Exception:
            failed = True
            await self._connection_status("error")
            raise
        finally:
            self._running = False
            tasks = [task for task in [connection_task, stop_task, *self._message_tasks] if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._message_tasks.clear()
            if not failed:
                await self._connection_status("stopped")

    async def stop(self) -> None:
        """请求结束运行，连接进程由运行协程统一回收。

        Args:
            无。
        """
        self._stop_event.set()

    async def _connection_status(self, status: str) -> None:
        """保存 SDK 真实连接状态。

        Args:
            status: 连接状态。
        """
        await self._sync_binding_state(runtime_state={"status": status, "bot_open_id": self._bot_open_id})

    async def _accept_event(self, event) -> None:
        """先持久化消息，再异步处理，避免 Agent 阻塞连接状态接收。

        Args:
            event: 规范化消息事件。
        """
        if not self.should_process_event(event):
            return
        message = await self.adapter.parse_event(event)
        message.user_id = self.binding.owner_user_id
        message.manager_user_id = self.binding.manager_user_id
        await self.service.accept_message(message)
        task = asyncio.create_task(self.service.process_message(message, self.adapter))
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)
        task.add_done_callback(self._log_event_processing_error)

    def _log_event_processing_error(self, future) -> None:
        """记录飞书入站消息转交后端处理时发生的异常。

        Args:
            future: 入站消息协程对应的 Future。
        """
        if future.cancelled():
            return
        try:
            future.result()
        except Exception:
            logger.exception("飞书消息处理失败: binding_id={}", self.binding.id)

    def _normalize_message_event(self, data: Any) -> dict[str, Any] | None:
        """把 SDK 对象转换成普通渠道事件。

        Args:
            data: SDK 对象或事件字典。
        """
        return normalize_event(data)

    async def _sync_binding_state(
        self,
        *,
        runtime_state: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> None:
        if self.store is None:
            return
        if self.binding.id is not None:
            if await self.store.get_binding(self.binding.id) is None:
                return
            binding = await self.store.update_binding(
                self.binding.id,
                credentials=credentials,
                runtime_state=runtime_state,
            )
        else:
            binding = await self.store.upsert_binding(
                channel=self.binding.channel,
                owner_user_id=self.binding.owner_user_id,
                manager_user_id=self.binding.manager_user_id,
                display_name=self.binding.display_name,
                credentials=credentials,
                config=self.binding.config,
                runtime_state=runtime_state,
                status="active",
            )
        self.binding = binding
        self.adapter.binding = binding

    def _mention_matches_current_bot(self, mention: Any) -> bool:
        if self._bot_open_id is None:
            return False
        if isinstance(mention, dict):
            mention_id = mention.get("id") or {}
            return str(mention_id.get("open_id") or "") == self._bot_open_id

        mention_id = getattr(mention, "id", None)
        open_id = getattr(mention_id, "open_id", None)
        return str(open_id or "") == self._bot_open_id


_feishu_runtimes: dict[int, FeishuRuntime] = {}


async def start_feishu_runtime(
    *,
    binding_id: int,
    store: ChannelStore,
) -> asyncio.Task[Any]:
    binding = await store.get_binding(binding_id)
    if binding is None:
        raise ValueError("Channel binding not found")

    runtime = _feishu_runtimes.get(binding_id)
    if runtime is None:
        runtime = FeishuRuntime(binding=binding, service=ChannelService(store=store), store=store)
        _feishu_runtimes[binding_id] = runtime

    manager = get_channel_runtime_manager()
    return await manager.start(f"feishu:{binding_id}", factory=runtime.run_forever, store=store)


async def stop_feishu_runtime(binding_id: int) -> None:
    runtime = _feishu_runtimes.pop(binding_id, None)
    if runtime is not None:
        await runtime.stop()
    manager = get_channel_runtime_manager()
    await manager.stop(f"feishu:{binding_id}")


async def start_saved_feishu_runtimes(*, store: ChannelStore | None = None) -> None:
    channel_store = store or get_channel_store()
    for binding in await channel_store.list_bindings(channel="feishu"):
        if not binding.credentials.get("app_id") or not binding.credentials.get("app_secret"):
            continue
        await start_feishu_runtime(binding_id=binding.id, store=channel_store)


async def stop_feishu_runtimes() -> None:
    binding_ids = list(_feishu_runtimes.keys())
    for binding_id in binding_ids:
        with suppress(Exception):
            await stop_feishu_runtime(binding_id)
