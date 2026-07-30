import asyncio

import pytest

from deepclaw.web_backend.channels.models import AgentEvent, ChannelMessage


class FakeAdapter:
    def __init__(self):
        self.sent: list[tuple[ChannelMessage, str]] = []
        self.edits: list[tuple[str, str]] = []

    async def send_message(self, message: ChannelMessage, text: str) -> str:
        self.sent.append((message, text))
        return f"reply_{len(self.sent)}"

    async def edit_message(self, reply_message_id: str, text: str) -> None:
        self.edits.append((reply_message_id, text))


class FakeTypingAdapter(FakeAdapter):
    supports_message_stream = False

    def __init__(self):
        super().__init__()
        self.typing_events: list[tuple[ChannelMessage, bool]] = []

    async def start_typing(self, message: ChannelMessage) -> None:
        self.typing_events.append((message, True))

    async def stop_typing(self, message: ChannelMessage) -> None:
        self.typing_events.append((message, False))


async def events(*items: AgentEvent):
    for item in items:
        yield item


@pytest.fixture
def message():
    return ChannelMessage(
        channel="feishu",
        message_id="msg_1",
        channel_user_id="ou_1",
        channel_conversation_id="chat_a",
        text="hello",
    )


def test_final_mode_sends_one_complete_reply(message):
    from deepclaw.web_backend.channels.dispatcher import ResponseDispatcher

    adapter = FakeAdapter()
    dispatcher = ResponseDispatcher()

    async def run():
        await dispatcher.dispatch(
            adapter=adapter,
            message=message,
            reply_mode="final",
            events=events(
                AgentEvent(event="token", data={"token": "hello"}),
                AgentEvent(event="tool_calls", data={"tool_calls": [{"name": "x"}]}),
                AgentEvent(event="token", data={"token": " world"}),
            ),
        )

    asyncio.run(run())

    assert adapter.sent == [(message, "hello world")]
    assert adapter.edits == []


def test_streaming_mode_edits_a_single_channel_message(message):
    from deepclaw.web_backend.channels.dispatcher import ResponseDispatcher

    adapter = FakeAdapter()
    dispatcher = ResponseDispatcher(min_interval_seconds=999, min_chars=5)

    async def run():
        await dispatcher.dispatch(
            adapter=adapter,
            message=message,
            reply_mode="streaming",
            events=events(
                AgentEvent(event="token", data={"token": "hi"}),
                AgentEvent(event="token", data={"token": " there"}),
            ),
        )

    asyncio.run(run())

    assert len(adapter.sent) == 1
    assert adapter.sent[0] == (message, "正在处理...")
    assert adapter.edits[-1] == ("reply_1", "hi there")


def test_streaming_mode_displays_tool_progress_without_tool_output(message):
    """流式回复仅显示工具状态，不泄露工具原始输出。"""
    from deepclaw.web_backend.channels.dispatcher import ResponseDispatcher

    adapter = FakeAdapter()
    dispatcher = ResponseDispatcher(min_interval_seconds=999, min_chars=999)

    async def run():
        await dispatcher.dispatch(
            adapter=adapter,
            message=message,
            reply_mode="streaming",
            events=events(
                AgentEvent(event="tool_calls", data={"tool_calls": [{"name": "search"}]}),
                AgentEvent(event="tool_output", data={"tool_output": ["secret result"]}),
                AgentEvent(event="token", data={"token": "answer"}),
            ),
        )

    asyncio.run(run())

    assert adapter.edits == [
        ("reply_1", "正在调用工具：search"),
        ("reply_1", "工具已完成，正在整理结果..."),
        ("reply_1", "answer"),
    ]


def test_interrupt_sends_manual_confirmation_fallback(message):
    from deepclaw.web_backend.channels.dispatcher import ResponseDispatcher

    adapter = FakeAdapter()
    dispatcher = ResponseDispatcher()

    async def run():
        await dispatcher.dispatch(
            adapter=adapter,
            message=message,
            reply_mode="final",
            events=events(AgentEvent(event="__interrupt__", data={"__interrupt__": {}})),
        )

    asyncio.run(run())

    assert len(adapter.sent) == 1
    assert "需要人工确认" in adapter.sent[0][1]

