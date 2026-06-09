import asyncio

from deepclaw.web_backend.channels.weixin_clawbot.runtime import fetch_startup_qrcode


class FakeQRCodeClient:
    def __init__(self, data):
        self.data = data
        self.called = False

    async def fetch_login_qrcode(self, *, local_token_list=None):
        self.called = True
        self.local_token_list = local_token_list
        return self.data


class FakeRuntimeClient:
    def __init__(self):
        self.status_calls = 0
        self.update_calls = 0
        self.tokens = []
        self.get_updates_bufs = []

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        self.status_calls += 1
        return {"bot_token": "token_1", "baseurl": "https://node.example.test"}

    async def get_updates(self, *, token, get_updates_buf=""):
        self.update_calls += 1
        self.tokens.append(token)
        self.get_updates_bufs.append(get_updates_buf)
        return {
            "get_updates_buf": "next_buf",
            "msgs": [
                {
                    "message_type": 1,
                    "message_id": "msg_1",
                    "from_user_id": "wx_user_1",
                    "context_token": "ctx_1",
                    "item_list": [{"text_item": {"text": "hello"}}],
                }
            ],
        }


class FakeAuthError(Exception):
    def __init__(self, status_code):
        self.response = type("Response", (), {"status_code": status_code})()


class FakeRecoveringRuntimeClient(FakeRuntimeClient):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    async def get_updates(self, *, token, get_updates_buf=""):
        if not self.failed_once:
            self.failed_once = True
            self.tokens.append(token)
            self.get_updates_bufs.append(get_updates_buf)
            raise FakeAuthError(401)
        return await super().get_updates(token=token, get_updates_buf=get_updates_buf)


class FakeService:
    def __init__(self):
        self.messages = []

    async def process_message(self, message, adapter):
        self.messages.append((message, adapter))


def test_fetch_startup_qrcode_prefers_qrcode_image_content():
    client = FakeQRCodeClient(
        {
            "qrcode": "raw_qrcode",
            "qrcode_img_content": "https://example.test/qrcode.png",
        }
    )

    result = asyncio.run(fetch_startup_qrcode(client=client))

    assert result["qrcode_url"] == "https://example.test/qrcode.png"
    assert result["qrcode"] == "raw_qrcode"
    assert client.local_token_list == []


def test_fetch_startup_qrcode_falls_back_to_qrcode():
    client = FakeQRCodeClient({"qrcode": "raw_qrcode"})

    result = asyncio.run(fetch_startup_qrcode(client=client))

    assert result["qrcode_url"] == "raw_qrcode"


def test_runtime_logs_in_then_processes_one_update_batch():
    from deepclaw.web_backend.channels.weixin_clawbot.runtime import WeixinClawBotRuntime

    client = FakeRuntimeClient()
    service = FakeService()
    runtime = WeixinClawBotRuntime(
        qrcode="qr-content",
        client=client,
        service=service,
        login_poll_interval_seconds=0,
        message_poll_interval_seconds=0,
    )

    asyncio.run(runtime.run_once())

    assert client.status_calls == 1
    assert client.update_calls == 1
    assert len(service.messages) == 1
    assert service.messages[0][0].channel == "weixin_clawbot"
    assert service.messages[0][0].text == "hello"


def test_runtime_reuses_persisted_token_after_process_restart():
    from deepclaw.web_backend.channels.store import ChannelStore
    from deepclaw.web_backend.channels.weixin_clawbot.runtime import (
        WeixinClawBotRuntime,
    )
    from deepclaw.web_backend.channels.weixin_clawbot.state import (
        weixin_clawbot_user_state_key,
    )

    store = ChannelStore("sqlite:///:memory:")
    store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key=weixin_clawbot_user_state_key("user_1"),
        data={
            "bot_token": "old_token",
            "base_url": "https://old-node.example.test",
            "get_updates_buf": "old_buf",
            "owner_user_id": "user_1",
        },
    )
    client = FakeRuntimeClient()
    service = FakeService()

    runtime = WeixinClawBotRuntime(
        qrcode="qr-content",
        client=client,
        service=service,
        store=store,
        state_key=weixin_clawbot_user_state_key("user_1"),
        owner_user_id="user_1",
        login_poll_interval_seconds=0,
        message_poll_interval_seconds=0,
    )

    asyncio.run(runtime.run_once())

    assert client.status_calls == 0
    assert client.tokens == ["old_token"]
    assert client.get_updates_bufs == ["old_buf"]
    assert client.base_url == "https://old-node.example.test"
    assert (
        store.get_runtime_state(
            channel="weixin_clawbot",
            state_key=weixin_clawbot_user_state_key("user_1"),
        ).data["get_updates_buf"]
        == "next_buf"
    )
    assert service.messages[0][0].user_id == "user_1"


def test_runtime_falls_back_to_qrcode_when_persisted_token_expires():
    from deepclaw.web_backend.channels.store import ChannelStore
    from deepclaw.web_backend.channels.weixin_clawbot.runtime import WeixinClawBotRuntime

    store = ChannelStore("sqlite:///:memory:")
    store.upsert_runtime_state(
        channel="weixin_clawbot",
        state_key="default",
        data={"bot_token": "expired_token", "get_updates_buf": "old_buf"},
    )
    client = FakeRecoveringRuntimeClient()
    service = FakeService()
    runtime = WeixinClawBotRuntime(
        qrcode="qr-content",
        client=client,
        service=service,
        store=store,
        login_poll_interval_seconds=0,
        message_poll_interval_seconds=0,
    )

    first_result = asyncio.run(runtime.run_once())
    second_result = asyncio.run(runtime.run_once())

    assert first_result is False
    assert second_result is True
    assert client.status_calls == 1
    assert client.tokens == ["expired_token", "token_1"]
    assert len(service.messages) == 1

