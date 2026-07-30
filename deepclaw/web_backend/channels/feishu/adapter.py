import json
import uuid
from typing import Any

from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway
from deepclaw.web_backend.channels.models import ChannelBinding, ChannelMessage


class FeishuAdapter:
    channel = "feishu"

    def __init__(
        self,
        *,
        binding: ChannelBinding | None = None,
        gateway: FeishuClientGateway | None = None,
    ):
        self.binding = binding
        self.gateway = gateway or FeishuClientGateway()

    async def parse_event(self, payload: dict) -> ChannelMessage:
        event = dict(payload.get("event") or payload)
        sender = dict((event.get("sender") or {}).get("sender_id") or {})
        message = dict(event.get("message") or payload)
        mentions = event.get("mentions") or []
        content = event.get("text")
        if content is None:
            content = self._extract_text(message)
        return ChannelMessage(
            channel=self.channel,
            message_id=str(message.get("message_id") or payload["message_id"]),
            channel_user_id=str(
                sender.get("open_id")
                or sender.get("user_id")
                or payload.get("channel_user_id")
            ),
            channel_conversation_id=str(
                (event.get("message") or {}).get("chat_id")
                or event.get("chat_id")
                or payload.get("channel_conversation_id")
            ),
            text=str(content or payload.get("text", "")),
            reply_mode=self._reply_mode(),
            message_type=str(message.get("message_type") or payload.get("message_type", "text")),
            binding_id=self.binding.id if self.binding is not None else None,
            raw={"event": event, "mentions": mentions},
        )

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        if self.binding is None:
            return f"feishu_reply_{uuid.uuid4().hex}"
        return await self.gateway.reply_markdown_card(
            binding=self.binding,
            message_id=message.message_id,
            text=text,
        )

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        if self.binding is None:
            return None
        await self.gateway.update_markdown_card(
            binding=self.binding,
            message_id=reply_message_id,
            text=text,
        )

    def _reply_mode(self) -> str:
        """根据飞书绑定配置确定当前消息的回复模式。

        Args:
            无。
        """
        if self.binding is not None and self.binding.config.get("streaming") is True:
            return "streaming"
        return "final"

    @staticmethod
    def _extract_text(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, dict):
            return str(content.get("text", ""))
        if isinstance(content, str):
            try:
                parsed_content = json.loads(content)
            except json.JSONDecodeError:
                return content
            if isinstance(parsed_content, dict):
                return str(parsed_content.get("text", ""))
        return str(content or "")
