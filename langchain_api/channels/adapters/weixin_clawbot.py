import base64
import random
import uuid
from collections.abc import Callable
from typing import Any, Awaitable

from langchain_api.channels.config import weixin_clawbot_settings
from langchain_api.channels.models import ChannelMessage


CHANNEL = "weixin_clawbot"
CHANNEL_VERSION = "2.4.3"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 3)
BOT_AGENT = "weixin-ClawBot-API/1.0.1 (langchain-api)"
MESSAGE_STATE_GENERATING = 1
MESSAGE_STATE_FINISH = 2


RequestJson = Callable[..., Awaitable[dict[str, Any]]]


def base_info() -> dict[str, str]:
    return {
        "channel_version": CHANNEL_VERSION,
        "bot_agent": BOT_AGENT,
    }


def make_headers(token: str | None = None) -> dict[str, str]:
    uin = str(random.randint(0, 0xFFFFFFFF))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class WeixinClawBotClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_json: RequestJson | None = None,
    ):
        self.base_url = (
            base_url or weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL
        ).rstrip("/")
        self.request_json = request_json or self._request_json

    async def fetch_login_qrcode(
        self, *, local_token_list: list[str] | None = None
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/get_bot_qrcode?bot_type=3",
            json_body={"local_token_list": local_token_list or []},
        )

    async def get_qrcode_status(
        self,
        *,
        qrcode: str,
        verify_code: str | None = None,
    ) -> dict[str, Any]:
        params = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code
        return await self.request_json(
            "GET",
            "ilink/bot/get_qrcode_status",
            params=params,
        )

    async def get_updates(
        self,
        *,
        token: str,
        get_updates_buf: str = "",
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/getupdates",
            token=token,
            json_body={"get_updates_buf": get_updates_buf, "base_info": base_info()},
        )

    async def get_config(
        self,
        *,
        token: str,
        ilink_user_id: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ilink_user_id": ilink_user_id,
            "base_info": base_info(),
        }
        if context_token:
            body["context_token"] = context_token
        return await self.request_json(
            "POST",
            "ilink/bot/getconfig",
            token=token,
            json_body=body,
        )

    async def send_typing(
        self,
        *,
        token: str,
        ilink_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/sendtyping",
            token=token,
            json_body={
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": base_info(),
            },
        )

    async def send_message(
        self,
        *,
        token: str,
        to_user_id: str,
        context_token: str,
        text: str,
        client_id: str | None = None,
        message_state: int = MESSAGE_STATE_FINISH,
    ) -> dict[str, Any]:
        client_id = client_id or f"langchain-api-weixin-{uuid.uuid4().hex}"
        return await self.request_json(
            "POST",
            "ilink/bot/sendmessage",
            token=token,
            json_body={
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": message_state,
                    "context_token": context_token,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                },
                "base_info": base_info(),
            },
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import httpx

        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.request(
                method,
                url,
                headers=make_headers(token),
                json=json_body,
                params=params,
            )
            response.raise_for_status()
            return response.json()


class WeixinClawBotAdapter:
    channel = CHANNEL
    supports_message_stream = False

    def __init__(
        self,
        *,
        token: str,
        client: WeixinClawBotClient | None = None,
    ):
        self.token = token
        self.client = client or WeixinClawBotClient()
        self._reply_context: dict[str, ChannelMessage] = {}
        self._typing_tickets: dict[str, str] = {}

    async def parse_event(self, payload: dict) -> ChannelMessage:
        return self.parse_update_message(payload)

    def parse_update_message(self, raw: dict[str, Any]) -> ChannelMessage:
        from_user_id = self._string_field(raw.get("from_user_id"))
        context_token = str(raw.get("context_token") or "")
        text = self._extract_text(raw)
        message_id = str(
            raw.get("message_id")
            or raw.get("msg_id")
            or raw.get("client_id")
            or f"{from_user_id}:{context_token}:{hash(text)}"
        )

        normalized_raw = dict(raw)
        normalized_raw["context_token"] = context_token
        return ChannelMessage(
            channel=self.channel,
            message_id=message_id,
            channel_user_id=from_user_id,
            channel_conversation_id=from_user_id,
            text=text,
            message_type=str(raw.get("message_type", "text")),
            raw=normalized_raw,
        )

    def iter_text_messages(self, updates: dict[str, Any]) -> list[ChannelMessage]:
        messages = []
        for raw in updates.get("msgs") or []:
            if raw.get("message_type") != 1:
                continue
            messages.append(self.parse_update_message(raw))
        return messages

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        return await self._send_channel_message(
            message,
            text,
            message_state=MESSAGE_STATE_FINISH,
        )

    async def start_message(self, message: ChannelMessage, text: str) -> str:
        client_id = f"langchain-api-weixin-{uuid.uuid4().hex}"
        return await self._send_channel_message(
            message,
            text,
            client_id=client_id,
            message_state=MESSAGE_STATE_GENERATING,
        )

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        message = self._reply_context.get(reply_message_id)
        if message is None:
            return None
        await self._send_channel_message(
            message,
            text,
            client_id=reply_message_id,
            message_state=MESSAGE_STATE_GENERATING,
        )

    async def finish_message(self, reply_message_id: str, text: str) -> None:
        message = self._reply_context.get(reply_message_id)
        if message is None:
            return None
        await self._send_channel_message(
            message,
            text,
            client_id=reply_message_id,
            message_state=MESSAGE_STATE_FINISH,
        )

    async def start_typing(self, message: ChannelMessage) -> None:
        context_token = self._context_token(message)
        config = await self.client.get_config(
            token=self.token,
            ilink_user_id=message.channel_user_id,
            context_token=context_token,
        )
        typing_ticket = config.get("typing_ticket")
        if not typing_ticket:
            return
        self._typing_tickets[message.message_id] = str(typing_ticket)
        await self.client.send_typing(
            token=self.token,
            ilink_user_id=message.channel_user_id,
            typing_ticket=str(typing_ticket),
            status=1,
        )

    async def stop_typing(self, message: ChannelMessage) -> None:
        typing_ticket = self._typing_tickets.pop(message.message_id, None)
        if not typing_ticket:
            return
        await self.client.send_typing(
            token=self.token,
            ilink_user_id=message.channel_user_id,
            typing_ticket=typing_ticket,
            status=2,
        )

    async def _send_channel_message(
        self,
        message: ChannelMessage,
        text: str,
        *,
        client_id: str | None = None,
        message_state: int = MESSAGE_STATE_FINISH,
    ) -> str:
        context_token = self._context_token(message)
        result = await self.client.send_message(
            token=self.token,
            to_user_id=message.channel_user_id,
            context_token=context_token,
            text=text,
            client_id=client_id,
            message_state=message_state,
        )
        reply_id = str(
            client_id
            or result.get("message_id")
            or result.get("client_id")
            or uuid.uuid4()
        )
        self._reply_context[reply_id] = message
        return reply_id

    def _context_token(self, message: ChannelMessage) -> str:
        if not message.raw:
            raise ValueError("Weixin ClawBot message missing raw context")
        context_token = message.raw.get("context_token")
        if not context_token:
            raise ValueError("Weixin ClawBot message missing context_token")
        return str(context_token)

    def _extract_text(self, raw: dict[str, Any]) -> str:
        container = raw.get("message_item") or raw
        item_list = container.get("item_list") or []
        if not item_list:
            return ""
        return str(item_list[0].get("text_item", {}).get("text", ""))

    def _string_field(self, value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("str") or value.get("string") or "")
        return str(value or "")
