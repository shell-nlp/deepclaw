import unittest

from langchain_api.channels.models import AgentEvent, ChannelMessage


class FakeAdapter:
    def __init__(self):
        self.sent: list[tuple[ChannelMessage, str]] = []
        self.edits: list[tuple[str, str]] = []

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        self.sent.append((message, text))
        return f"reply_{len(self.sent)}"

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        self.edits.append((reply_message_id, text))


async def events(*items: AgentEvent):
    for item in items:
        yield item


class ResponseDispatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = ChannelMessage(
            channel="feishu",
            message_id="msg_1",
            channel_user_id="ou_1",
            channel_conversation_id="chat_a",
            text="hello",
        )

    async def test_final_mode_sends_one_complete_reply(self):
        from langchain_api.channels.dispatcher import ResponseDispatcher

        adapter = FakeAdapter()
        dispatcher = ResponseDispatcher()

        await dispatcher.dispatch(
            adapter=adapter,
            message=self.message,
            reply_mode="final",
            events=events(
                AgentEvent(event="token", data={"token": "hello"}),
                AgentEvent(event="tool_calls", data={"tool_calls": [{"name": "x"}]}),
                AgentEvent(event="token", data={"token": " world"}),
            ),
        )

        self.assertEqual([(self.message, "hello world")], adapter.sent)
        self.assertEqual([], adapter.edits)

    async def test_streaming_mode_edits_a_single_channel_message(self):
        from langchain_api.channels.dispatcher import ResponseDispatcher

        adapter = FakeAdapter()
        dispatcher = ResponseDispatcher(min_interval_seconds=999, min_chars=5)

        await dispatcher.dispatch(
            adapter=adapter,
            message=self.message,
            reply_mode="streaming",
            events=events(
                AgentEvent(event="token", data={"token": "hi"}),
                AgentEvent(event="token", data={"token": " there"}),
            ),
        )

        self.assertEqual(1, len(adapter.sent))
        self.assertEqual((self.message, "正在处理..."), adapter.sent[0])
        self.assertEqual(("reply_1", "hi there"), adapter.edits[-1])

    async def test_interrupt_sends_manual_confirmation_fallback(self):
        from langchain_api.channels.dispatcher import ResponseDispatcher

        adapter = FakeAdapter()
        dispatcher = ResponseDispatcher()

        await dispatcher.dispatch(
            adapter=adapter,
            message=self.message,
            reply_mode="final",
            events=events(AgentEvent(event="__interrupt__", data={"__interrupt__": {}})),
        )

        self.assertEqual(1, len(adapter.sent))
        self.assertIn("需要人工确认", adapter.sent[0][1])


if __name__ == "__main__":
    unittest.main()
