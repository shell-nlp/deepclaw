import asyncio
from types import SimpleNamespace

import pytest


def test_channel_store_defaults_to_pg_database_url_when_configured(monkeypatch):
    import deepclaw.web_backend.db as db_module
    import deepclaw.web_backend.channels.store as channel_store_module

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        db_module,
        "settings",
        SimpleNamespace(
            PG_DATABASE_URL="postgresql://admin:admin@localhost:55432/deepclaw"
        ),
    )
    monkeypatch.setattr(
        channel_store_module,
        "create_async_engine_from_url",
        lambda db_url: captured.setdefault("db_url", db_url) or object(),
    )
    monkeypatch.setattr(
        channel_store_module,
        "build_async_sessionmaker",
        lambda engine: captured.setdefault("engine", engine) or object(),
    )

    channel_store_module.ChannelStore()

    assert captured["db_url"] == "postgresql://admin:admin@localhost:55432/deepclaw"


@pytest.fixture
def store():
    from deepclaw.web_backend.channels.store import ChannelStore

    return ChannelStore("sqlite:///:memory:")


def test_get_or_create_user_reuses_channel_user_mapping(store):
    async def _run():
        first = await store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            display_name="Alice",
        )
        second = await store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            display_name="Alice Renamed",
        )

        assert first.id == second.id
        assert first.user_id == second.user_id
        assert second.display_name == "Alice"

    asyncio.run(_run())


def test_get_or_create_session_reuses_conversation_user_mapping(store):
    async def _run():
        user = await store.get_or_create_user(
            channel="feishu",
            channel_user_id="ou_1",
            user_id="user_1",
        )

        first = await store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id=user.user_id,
        )
        second = await store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id=user.user_id,
            reply_mode="streaming",
        )

        assert first.id == second.id
        assert first.session_id == second.session_id
        assert second.reply_mode == "final"

    asyncio.run(_run())


def test_update_session_reply_mode_validates_values(store):
    async def _run():
        session = await store.get_or_create_session(
            channel="dingtalk",
            channel_conversation_id="cid_1",
            channel_user_id="ding_user_1",
            user_id="user_1",
        )

        updated = await store.update_session_reply_mode(session.session_id, "streaming")
        assert updated.reply_mode == "streaming"

        with pytest.raises(ValueError):
            await store.update_session_reply_mode(session.session_id, "verbose")

    asyncio.run(_run())


def test_message_record_uses_channel_message_as_logical_key(store):
    async def _run():
        from deepclaw.web_backend.channels.models import ChannelMessage

        message = ChannelMessage(
            channel="feishu",
            message_id="msg_1",
            channel_user_id="ou_1",
            channel_conversation_id="chat_a",
            text="hello",
        )

        first = await store.get_or_create_message_record(message)
        second = await store.get_or_create_message_record(message)
        done = await store.mark_message_status("feishu", "msg_1", "done")

        assert first.id == second.id
        assert second.status == "received"
        assert done.status == "done"

    asyncio.run(_run())


def test_runtime_state_upsert_reuses_channel_key(store):
    async def _run():
        first = await store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="default",
            data={"bot_token": "token_1", "get_updates_buf": ""},
        )
        second = await store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="default",
            data={"bot_token": "token_1", "get_updates_buf": "next_buf"},
        )
        loaded = await store.get_runtime_state(
            channel="weixin_clawbot",
            state_key="default",
        )

        assert first.id == second.id
        assert loaded is not None
        assert loaded.data == {"bot_token": "token_1", "get_updates_buf": "next_buf"}

    asyncio.run(_run())


def test_list_runtime_states_filters_by_channel(store):
    async def _run():
        await store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
            data={"bot_token": "token_1"},
        )
        await store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_2",
            data={"bot_token": "token_2"},
        )
        await store.upsert_runtime_state(
            channel="feishu",
            state_key="user:user_3",
            data={"token": "token_3"},
        )

        states = await store.list_runtime_states(channel="weixin_clawbot")

        assert [item.state_key for item in states] == ["user:user_1", "user:user_2"]

    asyncio.run(_run())


def test_delete_runtime_state_removes_channel_key(store):
    async def _run():
        await store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
            data={"bot_token": "token_1"},
        )

        deleted = await store.delete_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
        )
        missing = await store.get_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
        )

        assert deleted is True
        assert missing is None
        assert (
            await store.delete_runtime_state(
                channel="weixin_clawbot",
                state_key="user:user_1",
            )
            is False
        )

    asyncio.run(_run())


def test_binding_crud_and_runtime_state_merge(store):
    async def _run():
        binding = await store.create_binding(
            channel="feishu",
            owner_user_id="user_1",
            manager_user_id="user_1",
            display_name="我的飞书",
            credentials={"app_id": "cli_x", "app_secret": "sec_x"},
            config={"domain": "feishu", "streaming": True},
            runtime_state={"status": "offline"},
        )

        fetched = await store.get_binding(binding.id)
        assert fetched is not None
        assert fetched.channel == "feishu"
        assert fetched.credentials["app_id"] == "cli_x"
        assert fetched.runtime_state["status"] == "offline"

        updated = await store.update_binding_runtime_state(
            binding.id,
            {"status": "online", "ws": "connected"},
        )
        assert updated.runtime_state == {"status": "online", "ws": "connected"}

    asyncio.run(_run())


def test_list_bindings_supports_channel_and_owner_filters(store):
    async def _run():
        await store.create_binding(
            channel="weixin_clawbot",
            owner_user_id="user_1",
            manager_user_id="manager_1",
            credentials={"bot_token": "token_1"},
        )
        await store.create_binding(
            channel="weixin_clawbot",
            owner_user_id="user_2",
            manager_user_id="manager_2",
            credentials={"bot_token": "token_2"},
        )
        await store.create_binding(
            channel="feishu",
            owner_user_id="user_1",
            manager_user_id="manager_1",
            credentials={"app_id": "cli_x", "app_secret": "sec_x"},
        )

        bindings = await store.list_bindings(
            channel="weixin_clawbot", owner_user_id="user_1"
        )

        assert len(bindings) == 1
        assert bindings[0].channel == "weixin_clawbot"
        assert bindings[0].owner_user_id == "user_1"

    asyncio.run(_run())


def test_list_bindings_supports_owner_or_manager_participant_filter(store):
    async def _run():
        owned = await store.create_binding(
            channel="feishu",
            owner_user_id="user_1",
            manager_user_id="helper_1",
            display_name="owned_by_user_1",
            credentials={"app_id": "cli_owned", "app_secret": "sec_owned"},
        )
        managed = await store.create_binding(
            channel="feishu",
            owner_user_id="user_2",
            manager_user_id="user_1",
            display_name="managed_by_user_1",
            credentials={"app_id": "cli_managed", "app_secret": "sec_managed"},
        )
        await store.create_binding(
            channel="feishu",
            owner_user_id="user_3",
            manager_user_id="helper_3",
            display_name="hidden_from_user_1",
            credentials={"app_id": "cli_hidden", "app_secret": "sec_hidden"},
        )

        bindings = await store.list_bindings(
            channel="feishu",
            participant_user_id="user_1",
        )

        assert {item.id for item in bindings} == {owned.id, managed.id}

    asyncio.run(_run())


def test_upsert_binding_reuses_channel_and_owner(store):
    async def _run():
        first = await store.upsert_binding(
            channel="weixin_clawbot",
            owner_user_id="user_1",
            manager_user_id="manager_1",
            display_name="微信 1",
            credentials={"bot_token": "token_1"},
            runtime_state={"status": "pending"},
        )
        second = await store.upsert_binding(
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

    asyncio.run(_run())


def test_store_allows_multiple_bindings_for_same_owner_and_channel(store):
    async def _run():
        first = await store.create_binding(
            channel="feishu",
            owner_user_id="user_1",
            manager_user_id="user_1",
            display_name="市场部机器人",
            credentials={"app_id": "cli_a", "app_secret": "sec_a"},
            config={"domain": "feishu"},
        )
        second = await store.create_binding(
            channel="feishu",
            owner_user_id="user_1",
            manager_user_id="user_1",
            display_name="客服值班号",
            credentials={"app_id": "cli_b", "app_secret": "sec_b"},
            config={"domain": "feishu"},
        )

        items = await store.list_bindings(
            channel="feishu", owner_user_id="user_1"
        )

        assert first.id != second.id
        assert [item.display_name for item in items] == ["客服值班号", "市场部机器人"]

    asyncio.run(_run())


def test_store_updates_only_target_binding(store):
    async def _run():
        first = await store.create_binding(
            channel="weixin_clawbot",
            owner_user_id="user_1",
            manager_user_id="user_1",
            display_name="张三主号",
            credentials={},
        )
        second = await store.create_binding(
            channel="weixin_clawbot",
            owner_user_id="user_1",
            manager_user_id="user_1",
            display_name="李四代绑号",
            credentials={},
        )

        updated = await store.update_binding(
            second.id,
            display_name="李四备用机",
            runtime_state={"status": "pending"},
        )
        deleted = await store.delete_binding(second.id)
        remaining = await store.list_bindings(
            channel="weixin_clawbot", owner_user_id="user_1"
        )

        assert updated.display_name == "李四备用机"
        assert deleted is True
        assert (await store.get_binding(first.id)).display_name == "张三主号"
        assert [item.display_name for item in remaining] == ["张三主号"]

    asyncio.run(_run())
