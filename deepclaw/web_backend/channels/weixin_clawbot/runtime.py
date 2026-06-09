"""weixin Clawbot 代码文档参考：https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin?activeTab=readme"""

import asyncio
from typing import Any

from loguru import logger

from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    CHANNEL,
    WeixinClawBotAdapter,
)
from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    RUNTIME_STATE_KEY,
    weixin_clawbot_manager_user_id_from_state,
    weixin_clawbot_user_id_from_state_key,
)


async def fetch_startup_qrcode(
    *,
    client: WeixinClawBotClient | None = None,
    local_token_list: list[str] | None = None,
) -> dict[str, Any]:
    qrcode_client = client or WeixinClawBotClient()
    data = await qrcode_client.fetch_login_qrcode(local_token_list=local_token_list or [])
    return {
        "qrcode": data.get("qrcode"),
        "qrcode_url": data.get("qrcode_img_content") or data.get("qrcode"),
        "raw": data,
    }


def weixin_binding_state_key(binding_id: int) -> str:
    return f"binding:{binding_id}"


class WeixinClawBotRuntime:
    def __init__(
        self,
        *,
        binding_id: int | None = None,
        qrcode: str,
        client: WeixinClawBotClient | None = None,
        service: ChannelService | None = None,
        store: ChannelStore | None = None,
        state_key: str = RUNTIME_STATE_KEY,
        owner_user_id: str | None = None,
        login_poll_interval_seconds: float = 2,
        message_poll_interval_seconds: float = 1,
    ):
        self.qrcode = qrcode
        self.client = client or WeixinClawBotClient()
        self.service = service or ChannelService()
        self.store = store
        self.binding_id = binding_id
        self.state_key = (
            weixin_binding_state_key(binding_id)
            if binding_id is not None and state_key == RUNTIME_STATE_KEY
            else state_key
        )
        self.login_poll_interval_seconds = login_poll_interval_seconds
        self.message_poll_interval_seconds = message_poll_interval_seconds
        state = self._load_runtime_state()
        binding = self._load_binding()
        self.owner_user_id = (
            owner_user_id
            or self._optional_string(state.get("owner_user_id"))
            or self._optional_string(getattr(binding, "owner_user_id", None))
            or weixin_clawbot_user_id_from_state_key(state_key)
        )
        self.manager_user_id = self._optional_string(
            weixin_clawbot_manager_user_id_from_state(state_key, state)
        ) or self._optional_string(getattr(binding, "manager_user_id", None))
        self.qrcode = qrcode or self._optional_string(state.get("qrcode")) or self._binding_qrcode(binding) or ""
        self.bot_token: str | None = (
            self._optional_string(state.get("bot_token"))
            or self._binding_credential(binding, "bot_token")
        )
        self.get_updates_buf = str(
            state.get("get_updates_buf")
            or self._binding_runtime_state(binding, "get_updates_buf")
            or ""
        )
        if state.get("base_url"):
            self.client.base_url = str(state["base_url"]).rstrip("/")
        elif binding is not None:
            base_url = self._binding_credential(binding, "base_url")
            if base_url:
                self.client.base_url = base_url.rstrip("/")

    async def run_once(self) -> bool:
        if self.bot_token is None:
            status = await self.client.get_qrcode_status(qrcode=self.qrcode)
            token = status.get("bot_token")
            if not token:
                return False
            self.bot_token = str(token)
            if status.get("baseurl"):
                self.client.base_url = str(status["baseurl"]).rstrip("/")
            self._save_runtime_state()
            logger.info("微信 ClawBot 已扫码连接，开始轮询消息")

        adapter = WeixinClawBotAdapter(token=self.bot_token, client=self.client)
        try:
            updates = await self.client.get_updates(
                token=self.bot_token,
                get_updates_buf=self.get_updates_buf,
            )
        except Exception as exc:
            if not self._is_auth_error(exc):
                raise
            self.bot_token = None
            self.get_updates_buf = ""
            self._save_runtime_state()
            return False
        self.get_updates_buf = updates.get("get_updates_buf") or self.get_updates_buf
        self._save_runtime_state()
        for message in adapter.iter_text_messages(updates):
            message.user_id = self.owner_user_id
            message.manager_user_id = self.manager_user_id or self.owner_user_id
            message.binding_id = self.binding_id
            await self.service.process_message(message, adapter)
        return True

    async def run_forever(self) -> None:
        while True:
            try:
                has_token = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("微信 ClawBot 轮询失败：{}", exc)
                has_token = self.bot_token is not None

            interval = (
                self.message_poll_interval_seconds
                if has_token
                else self.login_poll_interval_seconds
            )
            await asyncio.sleep(interval)

    def _load_runtime_state(self) -> dict[str, Any]:
        if self.store is None:
            return {}
        state = self.store.get_runtime_state(
            channel=CHANNEL,
            state_key=self.state_key,
        )
        return dict(state.data) if state is not None and state.data else {}

    def _load_binding(self):
        if self.store is None or self.binding_id is None:
            return None
        return self.store.get_binding(self.binding_id)

    def _save_runtime_state(self) -> None:
        if self.store is None:
            return
        self.store.upsert_runtime_state(
            channel=CHANNEL,
            state_key=self.state_key,
            data={
                "bot_token": self.bot_token,
                "base_url": getattr(self.client, "base_url", None),
                "get_updates_buf": self.get_updates_buf,
                "owner_user_id": self.owner_user_id,
                "manager_user_id": self.manager_user_id,
            },
        )
        self._save_binding_state(
            status="connected" if self.bot_token else "pending",
        )

    def _save_binding_state(self, *, status: str) -> None:
        if self.store is None or not self.owner_user_id:
            return
        manager_user_id = self.manager_user_id or self.owner_user_id
        credentials = {
            key: value
            for key, value in {
                "bot_token": self.bot_token,
                "base_url": getattr(self.client, "base_url", None),
            }.items()
            if value
        }
        runtime_state = {
            "status": status,
            "qrcode": self.qrcode,
            "get_updates_buf": self.get_updates_buf,
        }
        if self.binding_id is not None:
            self.store.update_binding(
                self.binding_id,
                credentials=credentials,
                runtime_state=runtime_state,
                status="active",
            )
            return
        self.store.upsert_binding(
            channel=CHANNEL,
            owner_user_id=self.owner_user_id,
            manager_user_id=manager_user_id,
            display_name=f"Weixin ClawBot {self.owner_user_id}",
            credentials=credentials,
            runtime_state=runtime_state,
            status="active",
        )

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text or None

    def _is_auth_error(self, exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return status_code in {401, 403}

    def _binding_credential(self, binding: Any, key: str) -> str | None:
        if binding is None:
            return None
        return self._optional_string((binding.credentials or {}).get(key))

    def _binding_runtime_state(self, binding: Any, key: str) -> str | None:
        if binding is None:
            return None
        return self._optional_string((binding.runtime_state or {}).get(key))

    def _binding_qrcode(self, binding: Any) -> str | None:
        return self._binding_runtime_state(binding, "qrcode")
