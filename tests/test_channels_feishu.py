import asyncio


class FakeFeishuGateway:
    def __init__(self):
        self.replies: list[dict] = []

    async def reply_text(self, *, binding, message_id: str, text: str) -> str:
        self.replies.append(
            {
                "binding_id": binding.id,
                "message_id": message_id,
                "text": text,
            }
        )
        return f"feishu_reply_{message_id}"


def test_feishu_adapter_send_message_uses_binding_credentials():
    from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
    from deepclaw.web_backend.channels.models import ChannelBinding, ChannelMessage

    gateway = FakeFeishuGateway()
    binding = ChannelBinding(
        id=7,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
    )
    adapter = FeishuAdapter(binding=binding, gateway=gateway)
    message = ChannelMessage(
        channel="feishu",
        message_id="om_1",
        channel_user_id="ou_1",
        channel_conversation_id="oc_1",
        binding_id=7,
        text="hello",
    )

    reply_id = asyncio.run(adapter.send_message(message, "world"))

    assert reply_id == "feishu_reply_om_1"
    assert gateway.replies == [
        {"binding_id": 7, "message_id": "om_1", "text": "world"}
    ]


def test_feishu_runtime_skips_group_message_without_mention_when_policy_is_mention():
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.models import ChannelBinding

    binding = ChannelBinding(
        id=1,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"group_policy": "mention"},
    )
    runtime = FeishuRuntime(binding=binding)

    should_process = runtime.should_process_event(
        {
            "message_id": "om_1",
            "chat_id": "oc_1",
            "chat_type": "group",
            "mentions": [],
            "text": "hello group",
        }
    )

    assert should_process is False


def test_feishu_runtime_allows_p2p_message_even_when_policy_is_mention():
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.models import ChannelBinding

    binding = ChannelBinding(
        id=1,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"group_policy": "mention"},
    )
    runtime = FeishuRuntime(binding=binding)

    should_process = runtime.should_process_event(
        {
            "message_id": "om_1",
            "chat_id": "oc_1",
            "chat_type": "p2p",
            "mentions": [],
            "text": "hello direct",
        }
    )

    assert should_process is True


def test_feishu_runtime_mention_policy_requires_current_bot_open_id():
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.models import ChannelBinding

    binding = ChannelBinding(
        id=1,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"group_policy": "mention"},
    )
    runtime = FeishuRuntime(binding=binding)
    runtime._bot_open_id = "ou_bot_1"

    assert runtime.should_process_event(
        {
            "message_id": "om_1",
            "chat_id": "oc_1",
            "chat_type": "group",
            "mentions": [{"id": {"open_id": "ou_other"}}],
            "text": "hello @other",
        }
    ) is False

    assert runtime.should_process_event(
        {
            "message_id": "om_2",
            "chat_id": "oc_1",
            "chat_type": "group",
            "mentions": [{"id": {"open_id": "ou_bot_1"}}],
            "text": "hello @bot",
        }
    ) is True


def test_feishu_runtime_syncs_binding_runtime_state_on_start_and_stop():
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.store import ChannelStore

    class FakeGateway:
        async def fetch_bot_open_id(self, *, binding):
            return "ou_bot_1"

        def build_ws_client(self, *, binding, event_handler):
            class FakeWsClient:
                def start(self):
                    return None

            return FakeWsClient()

    store = ChannelStore("sqlite:///:memory:")
    binding = asyncio.run(store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"group_policy": "mention"},
    ))
    runtime = FeishuRuntime(binding=binding, store=store, gateway=FakeGateway())

    async def run():
        task = asyncio.create_task(runtime.run_forever())
        await asyncio.sleep(0.05)
        await runtime.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run())

    updated = asyncio.run(store.get_binding(binding.id))
    assert updated is not None
    assert updated.runtime_state["status"] == "stopped"
    assert updated.runtime_state["bot_open_id"] == "ou_bot_1"


def test_feishu_runtime_updates_only_target_binding_for_same_owner():
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.store import ChannelStore

    class FakeGateway:
        async def fetch_bot_open_id(self, *, binding):
            return "ou_bot_2"

        def build_ws_client(self, *, binding, event_handler):
            class FakeWsClient:
                def start(self):
                    return None

            return FakeWsClient()

    store = ChannelStore("sqlite:///:memory:")
    first = asyncio.run(store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="binding-a",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
        config={"group_policy": "mention"},
    ))
    second = asyncio.run(store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="binding-b",
        credentials={"app_id": "cli_b", "app_secret": "sec_b"},
        config={"group_policy": "mention"},
    ))
    runtime = FeishuRuntime(
        binding=second,
        store=store,
        gateway=FakeGateway(),
    )

    async def run():
        task = asyncio.create_task(runtime.run_forever())
        await asyncio.sleep(0.05)
        await runtime.stop()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run())

    refreshed_first = asyncio.run(store.get_binding(first.id))
    refreshed_second = asyncio.run(store.get_binding(second.id))
    assert refreshed_first is not None
    assert refreshed_second is not None
    assert refreshed_first.runtime_state == {}
    assert refreshed_second.runtime_state["status"] == "stopped"
    assert refreshed_second.runtime_state["bot_open_id"] == "ou_bot_2"
