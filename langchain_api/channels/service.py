import asyncio
from collections import defaultdict

from langchain_api.channels.adapters.base import ChannelAdapter
from langchain_api.channels.agent_client import AgentClient
from langchain_api.channels.dispatcher import ResponseDispatcher
from langchain_api.channels.models import ChannelMessage, ChannelMessageRecord
from langchain_api.channels.store import ChannelStore, get_channel_store


class ChannelService:
    def __init__(
        self,
        *,
        store: ChannelStore | None = None,
        agent_client: AgentClient | None = None,
        dispatcher: ResponseDispatcher | None = None,
    ):
        self.store = store or get_channel_store()
        self.agent_client = agent_client or AgentClient()
        self.dispatcher = dispatcher or ResponseDispatcher()
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def process_message(
        self, message: ChannelMessage, adapter: ChannelAdapter
    ) -> ChannelMessageRecord:
        record = self.store.get_or_create_message_record(message)
        if record.status in {"processing", "done", "failed"}:
            return record

        user = self.store.get_or_create_user(
            channel=message.channel,
            channel_user_id=self._routing_channel_user_id(message),
            user_id=message.user_id,
        )
        channel_session = self.store.get_or_create_session(
            channel=message.channel,
            channel_conversation_id=self._routing_conversation_id(message),
            channel_user_id=self._routing_channel_user_id(message),
            user_id=user.user_id,
        )

        async with self._locks[channel_session.session_id]:
            self.store.mark_message_status(message.channel, message.message_id, "processing")
            try:
                await self.dispatcher.dispatch(
                    adapter=adapter,
                    message=message,
                    reply_mode=channel_session.reply_mode,  # type: ignore[arg-type]
                    events=self.agent_client.stream(
                        query=message.text,
                        user_id=channel_session.user_id,
                        session_id=channel_session.session_id,
                    ),
                )
            except Exception as exc:
                return self.store.mark_message_status(
                    message.channel,
                    message.message_id,
                    "failed",
                    error=str(exc),
                )

            return self.store.mark_message_status(
                message.channel,
                message.message_id,
                "done",
            )

    def _routing_channel_user_id(self, message: ChannelMessage) -> str:
        if not message.user_id:
            return message.channel_user_id
        return f"{message.user_id}:{message.channel_user_id}"

    def _routing_conversation_id(self, message: ChannelMessage) -> str:
        if not message.user_id:
            return message.channel_conversation_id
        return f"{message.user_id}:{message.channel_conversation_id}"
