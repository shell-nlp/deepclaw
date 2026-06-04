import unittest

from langchain_api.channels.models import AgentEvent, ChannelMessage
from langchain_api.channels.store import ChannelStore


class FakeAgentClient:
    def __init__(self):
        self.calls: list[dict] = []

    async def stream(self, *, query: str, user_id: str, session_id: str):
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "session_id": session_id,
            }
        )
        yield AgentEvent(event="token", data={"token": "answer"})


class FakeDispatcher:
    def __init__(self):
        self.calls: list[dict] = []

    async def dispatch(self, *, adapter, message, reply_mode, events):
        tokens = []
        async for event in events:
            if event.event == "token" and event.data:
                tokens.append(event.data.get("token"))
        self.calls.append(
            {
                "adapter": adapter,
                "message": message,
                "reply_mode": reply_mode,
                "text": "".join(token for token in tokens if token),
            }
        )


class FakeAdapter:
    pass


class ChannelServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = ChannelStore("sqlite:///:memory:")
        self.agent_client = FakeAgentClient()
        self.dispatcher = FakeDispatcher()
        self.message = ChannelMessage(
            channel="feishu",
            message_id="msg_1",
            channel_user_id="ou_1",
            channel_conversation_id="chat_a",
            text="hello agent",
        )

    async def test_process_message_creates_mapping_and_dispatches_agent_response(self):
        from langchain_api.channels.service import ChannelService

        service = ChannelService(
            store=self.store,
            agent_client=self.agent_client,
            dispatcher=self.dispatcher,
        )

        record = await service.process_message(self.message, FakeAdapter())
        sessions = self.store.list_sessions()

        self.assertEqual("done", record.status)
        self.assertEqual(1, len(sessions))
        self.assertEqual("final", sessions[0].reply_mode)
        self.assertEqual("hello agent", self.agent_client.calls[0]["query"])
        self.assertEqual(sessions[0].user_id, self.agent_client.calls[0]["user_id"])
        self.assertEqual(sessions[0].session_id, self.agent_client.calls[0]["session_id"])
        self.assertEqual("answer", self.dispatcher.calls[0]["text"])

    async def test_duplicate_message_does_not_call_agent_twice(self):
        from langchain_api.channels.service import ChannelService

        service = ChannelService(
            store=self.store,
            agent_client=self.agent_client,
            dispatcher=self.dispatcher,
        )

        first = await service.process_message(self.message, FakeAdapter())
        second = await service.process_message(self.message, FakeAdapter())

        self.assertEqual("done", first.status)
        self.assertEqual("done", second.status)
        self.assertEqual(1, len(self.agent_client.calls))
        self.assertEqual(1, len(self.dispatcher.calls))

    async def test_user_id_override_isolated_channel_user_mappings(self):
        from langchain_api.channels.service import ChannelService

        service = ChannelService(
            store=self.store,
            agent_client=self.agent_client,
            dispatcher=self.dispatcher,
        )
        first = ChannelMessage(
            channel="weixin_clawbot",
            message_id="wx_msg_1",
            channel_user_id="same_wx_user",
            channel_conversation_id="same_wx_user",
            user_id="user_1",
            text="hello 1",
        )
        second = ChannelMessage(
            channel="weixin_clawbot",
            message_id="wx_msg_2",
            channel_user_id="same_wx_user",
            channel_conversation_id="same_wx_user",
            user_id="user_2",
            text="hello 2",
        )

        await service.process_message(first, FakeAdapter())
        await service.process_message(second, FakeAdapter())

        sessions = self.store.list_sessions()
        self.assertEqual(2, len(sessions))
        self.assertEqual(["user_1", "user_2"], [call["user_id"] for call in self.agent_client.calls])


if __name__ == "__main__":
    unittest.main()
