import uuid

from deepclaw.web_backend.channels.models import ChannelMessage


class FeishuAdapter:
    channel = "feishu"

    async def parse_event(self, payload: dict) -> ChannelMessage:
        return ChannelMessage(
            channel=self.channel,
            message_id=str(payload["message_id"]),
            channel_user_id=str(payload["channel_user_id"]),
            channel_conversation_id=str(payload["channel_conversation_id"]),
            text=str(payload.get("text", "")),
            message_type=str(payload.get("message_type", "text")),
            raw=payload,
        )

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        return f"feishu_reply_{uuid.uuid4().hex}"

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        return None
