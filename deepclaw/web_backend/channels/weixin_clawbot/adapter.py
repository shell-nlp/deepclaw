import uuid
from typing import Any

from deepclaw.web_backend.channels.models import ChannelMessage
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    MESSAGE_STATE_FINISH,
    MESSAGE_STATE_GENERATING,
    WeixinClawBotClient,
)


CHANNEL = "weixin_clawbot"


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
        client_id = f"deepclaw-weixin-{uuid.uuid4().hex}"
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
