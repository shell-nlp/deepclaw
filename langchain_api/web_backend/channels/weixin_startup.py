import asyncio
from typing import Any

from loguru import logger

from langchain_api.web_backend.channels.adapters.weixin_clawbot import (
    CHANNEL,
    WeixinClawBotAdapter,
    WeixinClawBotClient,
)
from langchain_api.web_backend.channels.service import ChannelService
from langchain_api.web_backend.channels.store import ChannelStore


RUNTIME_STATE_KEY = "default"


def weixin_clawbot_user_state_key(user_id: str) -> str:
    return f"user:{user_id}"


def weixin_clawbot_user_id_from_state_key(state_key: str) -> str | None:
    if not state_key.startswith("user:"):
        return None
    user_id = state_key.removeprefix("user:")
    return user_id or None


async def fetch_startup_qrcode(
    *,
    client: WeixinClawBotClient | None = None,
    local_token_list: list[str] | None = None,
) -> dict[str, Any]:
    qrcode_client = client or WeixinClawBotClient()
    data = await qrcode_client.fetch_login_qrcode(
        local_token_list=local_token_list or []
    )
    return {
        "qrcode": data.get("qrcode"),
        "qrcode_url": data.get("qrcode_img_content") or data.get("qrcode"),
        "raw": data,
    }


class WeixinClawBotRuntime:
    def __init__(
        self,
        *,
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
        self.state_key = state_key
        self.login_poll_interval_seconds = login_poll_interval_seconds
        self.message_poll_interval_seconds = message_poll_interval_seconds
        state = self._load_runtime_state()
        self.owner_user_id = (
            owner_user_id
            or self._optional_string(state.get("owner_user_id"))
            or weixin_clawbot_user_id_from_state_key(state_key)
        )
        self.bot_token: str | None = self._optional_string(state.get("bot_token"))
        self.get_updates_buf = str(state.get("get_updates_buf") or "")
        if state.get("base_url"):
            self.client.base_url = str(state["base_url"]).rstrip("/")

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
            },
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
