import asyncio
from typing import Any

from loguru import logger

from langchain_api.channels.adapters.weixin_clawbot import (
    WeixinClawBotAdapter,
    WeixinClawBotClient,
)
from langchain_api.channels.service import ChannelService


async def fetch_startup_qrcode(
    *, client: WeixinClawBotClient | None = None
) -> dict[str, Any]:
    qrcode_client = client or WeixinClawBotClient()
    data = await qrcode_client.fetch_login_qrcode(local_token_list=[])
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
        login_poll_interval_seconds: float = 2,
        message_poll_interval_seconds: float = 1,
    ):
        self.qrcode = qrcode
        self.client = client or WeixinClawBotClient()
        self.service = service or ChannelService()
        self.login_poll_interval_seconds = login_poll_interval_seconds
        self.message_poll_interval_seconds = message_poll_interval_seconds
        self.bot_token: str | None = None
        self.get_updates_buf = ""

    async def run_once(self) -> bool:
        if self.bot_token is None:
            status = await self.client.get_qrcode_status(qrcode=self.qrcode)
            token = status.get("bot_token")
            if not token:
                return False
            self.bot_token = str(token)
            if status.get("baseurl"):
                self.client.base_url = str(status["baseurl"]).rstrip("/")
            logger.info("微信 ClawBot 已扫码连接，开始轮询消息")

        adapter = WeixinClawBotAdapter(token=self.bot_token, client=self.client)
        updates = await self.client.get_updates(
            token=self.bot_token,
            get_updates_buf=self.get_updates_buf,
        )
        self.get_updates_buf = updates.get("get_updates_buf") or self.get_updates_buf
        for message in adapter.iter_text_messages(updates):
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
