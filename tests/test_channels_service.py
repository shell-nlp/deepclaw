import asyncio

import pytest

from deepclaw.web_backend.channels.models import AgentEvent, ChannelMessage
from deepclaw.web_backend.channels.store import ChannelStore


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


@pytest.fixture
def service_context():
    return {
        "store": ChannelStore("sqlite:///:memory:"),
        "agent_client": FakeAgentClient(),
        "dispatcher": FakeDispatcher(),
        "message": ChannelMessage(
            channel="feishu",
            message_id="msg_1",
            channel_user_id="ou_1",
            channel_conversation_id="chat_a",
            text="hello agent",
        ),
    }


def test_process_message_creates_mapping_and_dispatches_agent_response(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    message = service_context["message"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)

    record = asyncio.run(service.process_message(message, FakeAdapter()))
    sessions = asyncio.run(store.list_sessions())

    assert record.status == "done"
    assert len(sessions) == 1
    assert sessions[0].reply_mode == "final"
    assert agent_client.calls[0]["query"] == "hello agent"
    assert agent_client.calls[0]["user_id"] == sessions[0].user_id
    assert agent_client.calls[0]["session_id"] == sessions[0].session_id
    assert dispatcher.calls[0]["text"] == "answer"


def test_duplicate_message_does_not_call_agent_twice(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    message = service_context["message"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)

    first = asyncio.run(service.process_message(message, FakeAdapter()))
    second = asyncio.run(service.process_message(message, FakeAdapter()))

    assert first.status == "done"
    assert second.status == "done"
    assert len(agent_client.calls) == 1
    assert len(dispatcher.calls) == 1


def test_user_id_override_isolated_channel_user_mappings(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
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

    asyncio.run(service.process_message(first, FakeAdapter()))
    asyncio.run(service.process_message(second, FakeAdapter()))

    sessions = asyncio.run(store.list_sessions())
    assert len(sessions) == 2
    assert [call["user_id"] for call in agent_client.calls] == ["user_1", "user_2"]


def test_weixin_clawbot_new_sessions_default_to_streaming_reply_mode(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="wx_msg_1",
        channel_user_id="wx_user_1",
        channel_conversation_id="wx_user_1",
        user_id="user_1",
        text="hello streaming",
    )

    asyncio.run(service.process_message(message, FakeAdapter()))

    assert dispatcher.calls[0]["reply_mode"] == "streaming"
    assert asyncio.run(store.list_sessions())[0].reply_mode == "streaming"


def test_weixin_clawbot_default_reply_mode_can_be_configured_to_final(service_context, monkeypatch):
    from deepclaw.web_backend.channels import service as channel_service_module
    from deepclaw.web_backend.channels.service import ChannelService

    class FakeSettings:
        WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE = "final"

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="wx_msg_1",
        channel_user_id="wx_user_1",
        channel_conversation_id="wx_user_1",
        user_id="user_1",
        text="hello final",
    )

    monkeypatch.setattr(channel_service_module, "weixin_clawbot_settings", FakeSettings())
    asyncio.run(service.process_message(message, FakeAdapter()))

    assert dispatcher.calls[0]["reply_mode"] == "final"
    assert asyncio.run(store.list_sessions())[0].reply_mode == "final"


def test_message_reply_mode_overrides_existing_session_reply_mode(service_context):
    """渠道绑定指定流式模式时，会覆盖既有会话的最终回复模式。"""
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
    initial = service_context["message"]
    streaming = initial.model_copy(update={"message_id": "msg_2", "reply_mode": "streaming"})

    asyncio.run(service.process_message(initial, FakeAdapter()))
    asyncio.run(service.process_message(streaming, FakeAdapter()))

    assert dispatcher.calls[0]["reply_mode"] == "final"
    assert dispatcher.calls[1]["reply_mode"] == "streaming"


def test_binding_id_isolated_channel_user_mappings(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
    first_binding = asyncio.run(store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_a", "app_secret": "secret_a"},
    ))
    second_binding = asyncio.run(store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_b", "app_secret": "secret_b"},
    ))
    first = ChannelMessage(
        channel="feishu",
        message_id="fs_msg_1",
        channel_user_id="same_user",
        channel_conversation_id="same_chat",
        user_id="user_1",
        manager_user_id="user_1",
        binding_id=first_binding.id,
        text="hello 1",
    )
    second = ChannelMessage(
        channel="feishu",
        message_id="fs_msg_2",
        channel_user_id="same_user",
        channel_conversation_id="same_chat",
        user_id="user_1",
        manager_user_id="user_1",
        binding_id=second_binding.id,
        text="hello 2",
    )

    asyncio.run(service.process_message(first, FakeAdapter()))
    asyncio.run(service.process_message(second, FakeAdapter()))

    sessions = asyncio.run(store.list_sessions())
    assert len(sessions) == 2
    assert sorted(session.binding_id for session in sessions) == sorted(
        [first_binding.id, second_binding.id]
    )


def test_existing_binding_session_upgrades_guest_user_id_to_bound_user(service_context):
    from deepclaw.web_backend.channels.service import ChannelService

    store = service_context["store"]
    agent_client = service_context["agent_client"]
    dispatcher = service_context["dispatcher"]
    service = ChannelService(store=store, agent_client=agent_client, dispatcher=dispatcher)
    binding = asyncio.run(store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_bound",
        manager_user_id="user_bound",
        credentials={"bot_token": "token"},
    ))
    first = ChannelMessage(
        channel="weixin_clawbot",
        message_id="wx_msg_guest",
        channel_user_id="wx_user_same",
        channel_conversation_id="wx_chat_same",
        user_id="guest",
        manager_user_id="guest",
        binding_id=binding.id,
        text="hello as guest",
    )
    second = ChannelMessage(
        channel="weixin_clawbot",
        message_id="wx_msg_bound",
        channel_user_id="wx_user_same",
        channel_conversation_id="wx_chat_same",
        user_id="user_bound",
        manager_user_id="user_bound",
        binding_id=binding.id,
        text="hello as bound user",
    )

    asyncio.run(service.process_message(first, FakeAdapter()))
    asyncio.run(service.process_message(second, FakeAdapter()))

    sessions = asyncio.run(store.list_sessions())
    assert len(sessions) == 1
    assert sessions[0].user_id == "user_bound"
    assert [call["user_id"] for call in agent_client.calls] == ["guest", "user_bound"]
