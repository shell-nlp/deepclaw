import pytest


@pytest.fixture
def store():
    from langchain_api.channels.store import ChannelStore

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
    from langchain_api.channels.models import ChannelMessage

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
