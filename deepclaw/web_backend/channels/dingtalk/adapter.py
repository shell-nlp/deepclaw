from deepclaw.web_backend.channels.models import ChannelMessage


class DingTalkAdapter:
    channel = "dingtalk"

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
        """明确报告尚未接入的钉钉发送，禁止伪造投递成功。

        Args:
            message: 入站消息。
            text: 待发送正文。
        """
        raise NotImplementedError("钉钉消息发送尚未接入")

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        """明确报告钉钉消息更新尚未接入。

        Args:
            reply_message_id: 回复标识。
            text: 更新正文。
        """
        raise NotImplementedError("钉钉消息更新尚未接入")
