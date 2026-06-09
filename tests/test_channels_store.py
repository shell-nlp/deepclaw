import pytest


@pytest.fixture
def store():
    from deepclaw.web_backend.channels.store import ChannelStore

    return ChannelStore("sqlite:///:memory:")


def test_get_or_create_user_reuses_channel_user_mapping(store):
    first = store.get_or_create_user(
        channel="feishu",
        channel_user_id="ou_1",
        display_name="Alice",
    )
    second = store.get_or_create_user(
        channel="feishu",
        channel_user_id="ou_1",
        display_name="Alice Renamed",
    )

    assert first.id == second.id
    assert first.user_id == second.user_id
    assert second.display_name == "Alice"


def test_get_or_create_session_reuses_conversation_user_mapping(store):
    user = store.get_or_create_user(
        channel="feishu",
        channel_user_id="ou_1",
        user_id="user_1",
    )

    first = store.get_or_create_session(
        channel="feishu",
        channel_conversation_id="chat_a",
        channel_user_id="ou_1",
        user_id=user.user_id,
    )
    second = store.get_or_create_session(
        channel="feishu",
        channel_conversation_id="chat_a",
        channel_user_id="ou_1",
        user_id=user.user_id,
        reply_mode="streaming",
    )

    assert first.id == second.id
    assert first.session_id == second.session_id
    assert second.reply_mode == "final"


def test_update_session_reply_mode_validates_values(store):
    session = store.get_or_create_session(
        channel="dingtalk",
        channel_conversation_id="cid_1",
        channel_user_id="ding_user_1",
        user_id="user_1",
    )

    updated = store.update_session_reply_mode(session.session_id, "streaming")
    assert updated.reply_mode == "streaming"

    with pytest.raises(ValueError):
        store.update_session_reply_mode(session.session_id, "verbose")


def test_message_record_uses_channel_message_as_logical_key(store):
    from deepclaw.web_backend.channels.models import ChannelMessage

    message = ChannelMessage(
        channel="feishu",
        message_id="msg_1",
        channel_user_id="ou_1",
        channel_conversation_id="chat_a",
        text="hello",
    )

    first = store.get_or_create_message_record(message)
    second = store.get_or_create_message_record(message)
    done = store.mark_message_status("feishu", "msg_1", "done")

    assert first.id == second.id
    assert second.status == "received"
    assert done.status == "done"


def test_runtime_state_upsert_reuses_channel_key(store):
    first = store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="default",
        data={"bot_token": "token_1", "get_updates_buf": ""},
    )
    second = store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="default",
        data={"bot_token": "token_1", "get_updates_buf": "next_buf"},
    )
    loaded = store.get_runtime_state(
        channel="weixin_clawbot",
        state_key="default",
    )

    assert first.id == second.id
    assert loaded is not None
    assert loaded.data == {"bot_token": "token_1", "get_updates_buf": "next_buf"}


def test_list_runtime_states_filters_by_channel(store):
    store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_1",
        data={"bot_token": "token_1"},
    )
    store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_2",
        data={"bot_token": "token_2"},
    )
    store.upsert_runtime_state(
        channel="feishu",
        state_key="user:user_3",
        data={"token": "token_3"},
    )

    states = store.list_runtime_states(channel="weixin_clawbot")

    assert [item.state_key for item in states] == ["user:user_1", "user:user_2"]


def test_delete_runtime_state_removes_channel_key(store):
    store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_1",
        data={"bot_token": "token_1"},
    )

    deleted = store.delete_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_1",
    )
    missing = store.get_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_1",
    )

    assert deleted is True
    assert missing is None
    assert store.delete_runtime_state(
        channel="weixin_clawbot",
        state_key="user:user_1",
    ) is False


def test_binding_crud_and_runtime_state_merge(store):
    binding = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="我的飞书",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        config={"domain": "feishu", "streaming": True},
        runtime_state={"status": "offline"},
    )

    fetched = store.get_binding(binding.id)
    assert fetched is not None
    assert fetched.channel == "feishu"
    assert fetched.credentials["app_id"] == "cli_x"
    assert fetched.runtime_state["status"] == "offline"

    updated = store.update_binding_runtime_state(
        binding.id,
        {"status": "online", "ws": "connected"},
    )
    assert updated.runtime_state == {"status": "online", "ws": "connected"}


def test_list_bindings_supports_channel_and_owner_filters(store):
    store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="manager_1",
        credentials={"bot_token": "token_1"},
    )
    store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_2",
        manager_user_id="manager_2",
        credentials={"bot_token": "token_2"},
    )
    store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="manager_1",
        credentials={"app_id": "cli_x", "app_secret": "sec_x"},
    )

    bindings = store.list_bindings(channel="weixin_clawbot", owner_user_id="user_1")

    assert len(bindings) == 1
    assert bindings[0].channel == "weixin_clawbot"
    assert bindings[0].owner_user_id == "user_1"


def test_list_bindings_supports_owner_or_manager_participant_filter(store):
    owned = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="helper_1",
        display_name="owned_by_user_1",
        credentials={"app_id": "cli_owned", "app_secret": "sec_owned"},
    )
    managed = store.create_binding(
        channel="feishu",
        owner_user_id="user_2",
        manager_user_id="user_1",
        display_name="managed_by_user_1",
        credentials={"app_id": "cli_managed", "app_secret": "sec_managed"},
    )
    store.create_binding(
        channel="feishu",
        owner_user_id="user_3",
        manager_user_id="helper_3",
        display_name="hidden_from_user_1",
        credentials={"app_id": "cli_hidden", "app_secret": "sec_hidden"},
    )

    bindings = store.list_bindings(
        channel="feishu",
        participant_user_id="user_1",
    )

    assert {item.id for item in bindings} == {owned.id, managed.id}


def test_upsert_binding_reuses_channel_and_owner(store):
    first = store.upsert_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="manager_1",
        display_name="微信 1",
        credentials={"bot_token": "token_1"},
        runtime_state={"status": "pending"},
    )
    second = store.upsert_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="manager_2",
        display_name="微信 2",
        credentials={"bot_token": "token_2"},
        runtime_state={"status": "connected"},
    )

    assert first.id == second.id
    assert second.manager_user_id == "manager_2"
    assert second.display_name == "微信 2"
    assert second.credentials["bot_token"] == "token_2"
    assert second.runtime_state["status"] == "connected"

def test_store_allows_multiple_bindings_for_same_owner_and_channel(store):
    first = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="市场部机器人",
        credentials={"app_id": "cli_a", "app_secret": "sec_a"},
        config={"domain": "feishu"},
    )
    second = store.create_binding(
        channel="feishu",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="客服值班号",
        credentials={"app_id": "cli_b", "app_secret": "sec_b"},
        config={"domain": "feishu"},
    )

    items = store.list_bindings(channel="feishu", owner_user_id="user_1")

    assert first.id != second.id
    assert [item.display_name for item in items] == ["客服值班号", "市场部机器人"]


def test_store_updates_only_target_binding(store):
    first = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="张三主号",
        credentials={},
    )
    second = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="李四代绑号",
        credentials={},
    )

    updated = store.update_binding(
        second.id,
        display_name="李四备用机",
        runtime_state={"status": "pending"},
    )
    deleted = store.delete_binding(second.id)
    remaining = store.list_bindings(channel="weixin_clawbot", owner_user_id="user_1")

    assert updated.display_name == "李四备用机"
    assert deleted is True
    assert store.get_binding(first.id).display_name == "张三主号"
    assert [item.display_name for item in remaining] == ["张三主号"]
