import asyncio



class FakeFeishuGateway:
    def __init__(self):
        self.replies: list[dict] = []
        self.updates: list[dict] = []

    async def reply_markdown_card(self, *, binding, message_id: str, text: str) -> str:
        self.replies.append(
            {
                "binding_id": binding.id,
                "message_id": message_id,
                "text": text,
            }
        )
        return f"feishu_reply_{message_id}"

    async def update_markdown_card(self, *, binding, message_id: str, text: str) -> None:
        self.updates.append(
            {
                "binding_id": binding.id,
                "message_id": message_id,
                "text": text,
            }
        )


def test_feishu_adapter_sends_markdown_card_with_binding_credentials():
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


def test_feishu_adapter_updates_markdown_card_during_streaming():
    """飞书流式回复会更新同一张 Markdown 卡片。"""
    from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
    from deepclaw.web_backend.channels.models import ChannelBinding

    gateway = FakeFeishuGateway()
    binding = ChannelBinding(
        id=7,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
    )
    adapter = FeishuAdapter(binding=binding, gateway=gateway)

    asyncio.run(adapter.edit_message("om_reply", "# 更新中"))

    assert gateway.updates == [
        {"binding_id": 7, "message_id": "om_reply", "text": "# 更新中"}
    ]


def test_feishu_markdown_card_content_uses_lark_markdown():
    """飞书 interactive 卡片使用 lark_md 元素渲染 Markdown。"""
    import json

    from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway

    content = json.loads(FeishuClientGateway._markdown_card_content("## 标题\n\n- 项目"))

    assert content["elements"] == [
        {"tag": "div", "text": {"tag": "lark_md", "content": "**标题**"}},
        {"tag": "markdown", "content": "- 项目"},
    ]


def test_feishu_markdown_card_content_converts_tables_to_native_elements():
    """飞书卡片将标准 Markdown 表格转换为原生表格元素。"""
    import json

    from deepclaw.web_backend.channels.feishu.client import FeishuClientGateway

    content = json.loads(
        FeishuClientGateway._markdown_card_content(
            "| 名称 | 数量 |\n| --- | --- |\n| 苹果 | 3 |"
        )
    )

    assert content["elements"] == [
        {
            "tag": "table",
            "page_size": 2,
            "columns": [
                {"tag": "column", "name": "c0", "display_name": "名称", "width": "auto"},
                {"tag": "column", "name": "c1", "display_name": "数量", "width": "auto"},
            ],
            "rows": [{"c0": "苹果", "c1": "3"}],
        }
    ]


def test_feishu_adapter_extracts_text_from_sdk_json_content():
    """飞书 SDK 的 JSON 字符串内容会被还原成纯文本。"""
    from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter

    assert FeishuAdapter._extract_text({"content": '{"text":"hello"}'}) == "hello"


def test_feishu_adapter_uses_streaming_mode_when_enabled():
    """启用飞书流式配置后，入站消息使用流式分发。"""
    from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
    from deepclaw.web_backend.channels.models import ChannelBinding

    binding = ChannelBinding(
        id=7,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"streaming": True},
    )
    adapter = FeishuAdapter(binding=binding)

    message = asyncio.run(
        adapter.parse_event(
            {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": '{"text":"hello"}',
                "sender": {"sender_id": {"open_id": "ou_1"}},
            }
        )
    )

    assert message.reply_mode == "streaming"


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


def test_feishu_normalizes_message_mentions_from_message_object():
    """群聊提及信息从消息对象读取，能够匹配当前机器人。"""
    from types import SimpleNamespace as NS
    from deepclaw.web_backend.channels.feishu.connection import normalize_event

    result = normalize_event(NS(event=NS(
        message=NS(message_id="m", mentions=[NS(id=NS(open_id="bot"))]),
        sender=NS(sender_id=NS(open_id="sender")),
    )))
    assert result["mentions"] == [{"id": {"open_id": "bot"}}]


def test_feishu_runtime_passes_normalized_event_to_adapter():
    """飞书长连接事件会被适配为可持久化的渠道消息。"""
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.models import ChannelBinding

    class FakeService:
        """记录转交给渠道服务的消息。"""

        def __init__(self):
            """初始化消息记录容器。

            Args:
                无。
            """
            self.messages = []

        async def process_message(self, message, adapter):
            """记录飞书消息及其适配器。

            Args:
                message: 已解析的渠道消息。
                adapter: 用于回复消息的渠道适配器。
            """
            self.messages.append((message, adapter))

    binding = ChannelBinding(
        id=1,
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="manager_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
    )
    service = FakeService()
    runtime = FeishuRuntime(binding=binding, service=service)

    asyncio.run(
        runtime.handle_event(
            {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": '{"text":"hello"}',
                "sender": {"sender_id": {"open_id": "ou_1"}},
            }
        )
    )

    message, adapter = service.messages[0]
    assert message.message_id == "om_1"
    assert message.channel_user_id == "ou_1"
    assert message.channel_conversation_id == "oc_1"
    assert message.text == "hello"
    assert message.user_id == "user_1"
    assert adapter is runtime.adapter


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


def test_feishu_runtime_syncs_binding_runtime_state_on_start_and_stop(tmp_path):
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.store import ChannelStore

    connected = asyncio.Event()

    class FakeGateway:
        async def fetch_bot_open_id(self, *, binding):
            return "ou_bot_1"

        async def run_connection(self, binding, on_event, on_status):
            """模拟持续连接并报告真实连接状态。

            Args:
                binding: 渠道绑定。
                on_event: 入站事件回调。
                on_status: 连接状态回调。
            """
            await on_status("connected")
            connected.set()
            await asyncio.Event().wait()

    store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
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
        try:
            await asyncio.wait_for(connected.wait(), timeout=3)
        finally:
            await runtime.stop()
            await asyncio.wait_for(task, timeout=3)

    asyncio.run(run())

    updated = asyncio.run(store.get_binding(binding.id))
    assert updated is not None
    assert updated.runtime_state["status"] == "stopped"
    assert updated.runtime_state["bot_open_id"] == "ou_bot_1"


def test_feishu_runtime_updates_only_target_binding_for_same_owner(tmp_path):
    from deepclaw.web_backend.channels.feishu.runtime import FeishuRuntime
    from deepclaw.web_backend.channels.store import ChannelStore

    connected = asyncio.Event()

    class FakeGateway:
        async def fetch_bot_open_id(self, *, binding):
            return "ou_bot_2"

        async def run_connection(self, binding, on_event, on_status):
            """模拟持续连接并报告真实连接状态。

            Args:
                binding: 渠道绑定。
                on_event: 入站事件回调。
                on_status: 连接状态回调。
            """
            await on_status("connected")
            connected.set()
            await asyncio.Event().wait()

    store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
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
        try:
            await asyncio.wait_for(connected.wait(), timeout=3)
        finally:
            await runtime.stop()
            await asyncio.wait_for(task, timeout=3)

    asyncio.run(run())

    refreshed_first = asyncio.run(store.get_binding(first.id))
    refreshed_second = asyncio.run(store.get_binding(second.id))
    assert refreshed_first is not None
    assert refreshed_second is not None
    assert refreshed_first.runtime_state == {}
    assert refreshed_second.runtime_state["status"] == "stopped"
    assert refreshed_second.runtime_state["bot_open_id"] == "ou_bot_2"
