import asyncio
import threading
from contextlib import suppress
from typing import Any

from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway
from deepclaw.web_backend.channels.feishu.settings import feishu_settings
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
        self.service = service or ChannelService()
        self.store = store
        self.gateway = gateway or FeishuClientGateway()
        self.adapter = FeishuAdapter(binding=binding, gateway=self.gateway)
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_thread: threading.Thread | None = None
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
        message = await self.adapter.parse_event({"event": event})
        message.user_id = self.binding.owner_user_id
        message.manager_user_id = self.binding.manager_user_id
        await self.service.process_message(message, self.adapter)

    async def run_forever(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._sync_binding_state(runtime_state={"status": "starting"})
        self._bot_open_id = await self.gateway.fetch_bot_open_id(binding=self.binding)
        self._sync_binding_state(
            runtime_state={
                "status": "connected",
                "bot_open_id": self._bot_open_id,
            }
        )
        self._start_ws_thread()
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        self._sync_binding_state(runtime_state={"status": "stopped", "bot_open_id": self._bot_open_id})

    def _start_ws_thread(self) -> None:
        if self._ws_thread is not None and self._ws_thread.is_alive():
            return

        def run_ws():
            try:
                self._run_ws_loop()
            except Exception:
                return

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

    def _run_ws_loop(self) -> None:
        while self._running:
            try:
                ws_client = self.gateway.build_ws_client(
                    binding=self.binding,
                    event_handler=self._build_event_handler(),
                )
                ws_client.start()
            except Exception:
                if not self._running:
                    break
                threading.Event().wait(feishu_settings.FEISHU_RUNTIME_RECONNECT_SECONDS)

    def _build_event_handler(self):
        lark = self.gateway._import_lark()
        builder = lark.EventDispatcherHandler.builder("", "")
        register = getattr(builder, "register_p2_im_message_receive_v1", None)
        if callable(register):
            builder = register(self._on_message_sync)
        return builder.build()

    def _on_message_sync(self, data) -> None:
        if not self._running:
            return
        event = self._normalize_message_event(data)
        if event is None:
            return
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.handle_event(event), self._loop)

    def _normalize_message_event(self, data: Any) -> dict[str, Any] | None:
        event = getattr(getattr(data, "event", None), "message", None)
        root = getattr(data, "event", None)
        if root is None:
            if isinstance(data, dict):
                return data
            return None

        sender = getattr(getattr(root, "sender", None), "sender_id", None)
        mentions = getattr(root, "mentions", None) or []
        return {
            "message_id": getattr(event, "message_id", None),
            "chat_id": getattr(event, "chat_id", None),
            "chat_type": getattr(event, "chat_type", None),
            "message_type": getattr(event, "message_type", None),
            "content": getattr(event, "content", None),
            "sender": {
                "sender_id": {
                    "open_id": getattr(sender, "open_id", None),
                    "user_id": getattr(sender, "user_id", None),
                }
            },
            "mentions": mentions,
        }

    def _sync_binding_state(
        self,
        *,
        runtime_state: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> None:
        if self.store is None:
            return
        if self.binding.id is not None:
            binding = self.store.update_binding(
                self.binding.id,
                display_name=self.binding.display_name,
                credentials=credentials,
                config=self.binding.config,
                runtime_state=runtime_state,
                status="active",
            )
        else:
            binding = self.store.upsert_binding(
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
    binding = store.get_binding(binding_id)
    if binding is None:
        raise ValueError("Channel binding not found")

    runtime = _feishu_runtimes.get(binding_id)
    if runtime is None:
        runtime = FeishuRuntime(binding=binding, service=ChannelService(store=store), store=store)
        _feishu_runtimes[binding_id] = runtime

    manager = get_channel_runtime_manager()
    return await manager.start(f"feishu:{binding_id}", runtime.run_forever())


async def stop_feishu_runtime(binding_id: int) -> None:
    runtime = _feishu_runtimes.pop(binding_id, None)
    if runtime is not None:
        await runtime.stop()
    manager = get_channel_runtime_manager()
    await manager.stop(f"feishu:{binding_id}")


async def start_saved_feishu_runtimes(*, store: ChannelStore | None = None) -> None:
    channel_store = store or get_channel_store()
    for binding in channel_store.list_bindings(channel="feishu"):
        if not binding.credentials.get("app_id") or not binding.credentials.get("app_secret"):
            continue
        await start_feishu_runtime(binding_id=binding.id, store=channel_store)


async def stop_feishu_runtimes() -> None:
    binding_ids = list(_feishu_runtimes.keys())
    for binding_id in binding_ids:
        with suppress(Exception):
            await stop_feishu_runtime(binding_id)
