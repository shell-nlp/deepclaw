import asyncio
import importlib

import pytest

from deepclaw.web_backend.channels.weixin_clawbot import lifespan as weixin_lifespan_module


def test_channels_lifespan_compat_module_is_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("deepclaw.web_backend.channels.lifespan")


def test_channel_lifespan_starts_saved_weixin_user_runtimes_and_cancels_tasks(monkeypatch):
    started = []
    cancelled = []
    captured = {}

    class FakeSettings:
        WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP = True
        WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP = True
        WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS = 3
        WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS = 4

    class FakeState:
        def __init__(self, state_key, token):
            self.state_key = state_key
            self.data = {"bot_token": token, "owner_user_id": state_key.removeprefix("user:")}

    class FakeStore:
        def list_runtime_states(self, *, channel):
            captured["channel"] = channel
            return [
                FakeState("user:user_1", "token_1"),
                FakeState("user:user_2", "token_2"),
                FakeState("default", "legacy_token"),
            ]

    class FakeRuntime:
        def __init__(
            self,
            *,
            qrcode,
            store,
            state_key,
            owner_user_id,
            login_poll_interval_seconds,
            message_poll_interval_seconds,
        ):
            captured.setdefault("runtimes", []).append(
                {
                    "qrcode": qrcode,
                    "store": store,
                    "state_key": state_key,
                    "owner_user_id": owner_user_id,
                    "login_poll_interval_seconds": login_poll_interval_seconds,
                    "message_poll_interval_seconds": message_poll_interval_seconds,
                }
            )

        async def run_forever(self):
            started.append(True)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

    fake_store = FakeStore()
    monkeypatch.setattr(weixin_lifespan_module, "weixin_clawbot_settings", FakeSettings())
    monkeypatch.setattr(weixin_lifespan_module, "get_channel_store", lambda: fake_store)
    monkeypatch.setattr(weixin_lifespan_module, "WeixinClawBotRuntime", FakeRuntime)
    monkeypatch.setattr(
        weixin_lifespan_module,
        "start_saved_feishu_runtimes",
        lambda *, store: asyncio.sleep(0),
    )
    monkeypatch.setattr(
        weixin_lifespan_module,
        "stop_feishu_runtimes",
        lambda: asyncio.sleep(0),
    )

    async def run():
        async with weixin_lifespan_module.channel_lifespan():
            for _ in range(10):
                if len(started) == 2:
                    break
                await asyncio.sleep(0.01)

    asyncio.run(run())

    runtimes = captured["runtimes"]
    assert len(cancelled) == 2
    assert captured["channel"] == "weixin_clawbot"
    assert [item["state_key"] for item in runtimes] == ["user:user_1", "user:user_2"]
    assert [item["owner_user_id"] for item in runtimes] == ["user_1", "user_2"]
    assert all(item["store"] is fake_store for item in runtimes)
    assert all(item["login_poll_interval_seconds"] == 3 for item in runtimes)
    assert all(item["message_poll_interval_seconds"] == 4 for item in runtimes)


def test_channel_lifespan_starts_and_stops_saved_feishu_runtimes(monkeypatch):
    captured = {}

    class FakeSettings:
        WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP = True
        WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP = False

    class FakeStore:
        pass

    fake_store = FakeStore()

    async def fake_start_saved_feishu_runtimes(*, store):
        captured["start_store"] = store

    async def fake_stop_feishu_runtimes():
        captured["stopped"] = True

    monkeypatch.setattr(weixin_lifespan_module, "weixin_clawbot_settings", FakeSettings())
    monkeypatch.setattr(weixin_lifespan_module, "get_channel_store", lambda: fake_store)
    monkeypatch.setattr(weixin_lifespan_module, "start_saved_feishu_runtimes", fake_start_saved_feishu_runtimes)
    monkeypatch.setattr(weixin_lifespan_module, "stop_feishu_runtimes", fake_stop_feishu_runtimes)

    async def run():
        async with weixin_lifespan_module.channel_lifespan():
            await asyncio.sleep(0)

    asyncio.run(run())

    assert captured["start_store"] is fake_store
    assert captured["stopped"] is True


def test_start_saved_weixin_runtimes_prefers_binding_records(monkeypatch):
    from deepclaw.web_backend.channels.store import ChannelStore

    store = ChannelStore("sqlite:///:memory:")
    first = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="张三主号",
        credentials={"bot_token": "token_1"},
        runtime_state={"qrcode": "qr_1", "status": "connected"},
    )
    second = store.create_binding(
        channel="weixin_clawbot",
        owner_user_id="user_1",
        manager_user_id="user_1",
        display_name="李四代绑号",
        credentials={"bot_token": "token_2"},
        runtime_state={"qrcode": "qr_2", "status": "connected"},
    )
    started = []

    async def fake_start_runtime(*, binding_id, store):
        started.append(binding_id)

    monkeypatch.setattr(
        weixin_lifespan_module,
        "start_weixin_binding_runtime",
        fake_start_runtime,
        raising=False,
    )

    asyncio.run(weixin_lifespan_module.start_saved_weixin_clawbot_runtimes(store=store))

    assert sorted(started) == [first.id, second.id]

