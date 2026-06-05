import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from langchain_api.channels.models import ChannelMessageRecord
from langchain_api.channels.store import ChannelStore


class FakeService:
    def __init__(self):
        self.calls = []

    async def process_message(self, message, adapter):
        self.calls.append((message, adapter))
        return ChannelMessageRecord(
            channel=message.channel,
            message_id=message.message_id,
            channel_conversation_id=message.channel_conversation_id,
            channel_user_id=message.channel_user_id,
            status="done",
        )


class FakeWeixinClient:
    async def fetch_login_qrcode(self, *, local_token_list=None):
        self.local_token_list = local_token_list
        return {
            "qrcode": "qr-content",
            "qrcode_img_content": "https://example.test/qrcode.png",
        }

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        self.qrcode = qrcode
        self.verify_code = verify_code
        return {
            "status": "confirmed",
            "bot_token": "token_1",
            "baseurl": "https://node.example.test",
        }

    async def get_updates(self, *, token, get_updates_buf=""):
        self.token = token
        self.get_updates_buf = get_updates_buf
        return {
            "get_updates_buf": "next_buf",
            "msgs": [
                {
                    "message_type": 1,
                    "message_id": "wx_msg_1",
                    "from_user_id": "wx_user_1",
                    "context_token": "ctx_1",
                    "item_list": [{"text_item": {"text": "你好"}}],
                },
                {
                    "message_type": 2,
                    "message_id": "ignored",
                    "from_user_id": "wx_user_1",
                    "context_token": "ctx_1",
                    "item_list": [{"text_item": {"text": "ignore"}}],
                },
            ],
        }


class TimeoutWeixinClient:
    async def fetch_login_qrcode(self, *, local_token_list=None):
        raise httpx.ReadTimeout("timed out")

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        raise httpx.ReadTimeout("timed out")


class ChannelsRouterTest(unittest.TestCase):
    def test_session_config_routes_list_and_update_reply_mode(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        session = store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id="user_1",
        )
        app = FastAPI()
        app.include_router(create_channels_router(store=store))
        client = TestClient(app)

        list_response = client.get("/api/channels/sessions")
        self.assertEqual(200, list_response.status_code)
        self.assertEqual(1, list_response.json()["total"])

        patch_response = client.patch(
            f"/api/channels/sessions/{session.session_id}",
            json={"reply_mode": "streaming"},
        )
        self.assertEqual(200, patch_response.status_code)
        self.assertEqual("streaming", patch_response.json()["reply_mode"])

    def test_session_config_rejects_invalid_reply_mode(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        session = store.get_or_create_session(
            channel="feishu",
            channel_conversation_id="chat_a",
            channel_user_id="ou_1",
            user_id="user_1",
        )
        app = FastAPI()
        app.include_router(create_channels_router(store=store))
        client = TestClient(app)

        response = client.patch(
            f"/api/channels/sessions/{session.session_id}",
            json={"reply_mode": "verbose"},
        )

        self.assertEqual(422, response.status_code)

    def test_feishu_webhook_accepts_normalized_payload(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        service = FakeService()
        app = FastAPI()
        app.include_router(create_channels_router(store=store, service=service))
        client = TestClient(app)

        response = client.post(
            "/api/channels/feishu/events",
            json={
                "message_id": "msg_1",
                "channel_user_id": "ou_1",
                "channel_conversation_id": "chat_a",
                "text": "hello",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "accepted"}, response.json())
        self.assertEqual(1, len(service.calls))
        self.assertEqual("feishu", service.calls[0][0].channel)

    def test_weixin_clawbot_poll_accepts_text_updates(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        service = FakeService()
        weixin_client = FakeWeixinClient()
        app = FastAPI()
        app.include_router(
            create_channels_router(
                store=store,
                service=service,
                weixin_client=weixin_client,
            )
        )
        client = TestClient(app)

        response = client.post(
            "/api/channels/weixin-clawbot/poll",
            json={"bot_token": "token_1", "get_updates_buf": "old_buf"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"status": "accepted", "accepted": 1, "get_updates_buf": "next_buf"},
            response.json(),
        )
        self.assertEqual("token_1", weixin_client.token)
        self.assertEqual("old_buf", weixin_client.get_updates_buf)
        self.assertEqual(1, len(service.calls))
        self.assertEqual("weixin_clawbot", service.calls[0][0].channel)

    def test_weixin_clawbot_qrcode_routes_return_link_and_status(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        weixin_client = FakeWeixinClient()
        app = FastAPI()
        app.include_router(
            create_channels_router(store=store, weixin_client=weixin_client)
        )
        client = TestClient(app)

        qrcode_response = client.post(
            "/api/channels/weixin-clawbot/qrcode",
            json={"local_token_list": ["old_token"]},
        )
        status_response = client.get(
            "/api/channels/weixin-clawbot/qrcode/status",
            params={"qrcode": "qr-content", "verify_code": "1234"},
        )

        self.assertEqual(200, qrcode_response.status_code)
        self.assertEqual(
            {
                "qrcode": "qr-content",
                "qrcode_url": "https://example.test/qrcode.png",
                "raw": {
                    "qrcode": "qr-content",
                    "qrcode_img_content": "https://example.test/qrcode.png",
                },
            },
            qrcode_response.json(),
        )
        self.assertEqual(["old_token"], weixin_client.local_token_list)
        self.assertEqual(200, status_response.status_code)
        self.assertEqual("confirmed", status_response.json()["status"])
        self.assertEqual("token_1", status_response.json()["bot_token"])
        self.assertEqual("qr-content", weixin_client.qrcode)
        self.assertEqual("1234", weixin_client.verify_code)

    def test_weixin_clawbot_user_qrcode_routes_persist_user_runtime_state(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        weixin_client = FakeWeixinClient()
        started = {}

        async def fake_start_runtime(*, state_key, store, qrcode):
            started["state_key"] = state_key
            started["store"] = store
            started["qrcode"] = qrcode
            return None

        app = FastAPI()
        app.include_router(
            create_channels_router(store=store, weixin_client=weixin_client)
        )
        client = TestClient(app)

        with patch(
            "langchain_api.api.routers.channels.start_weixin_clawbot_runtime",
            fake_start_runtime,
        ):
            qrcode_response = client.post(
                "/api/channels/weixin-clawbot/users/user_1/qrcode"
            )
            status_response = client.get(
                "/api/channels/weixin-clawbot/users/user_1/qrcode/status"
            )

        self.assertEqual(200, qrcode_response.status_code)
        self.assertEqual(200, status_response.status_code)
        runtime_state = store.get_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
        )
        self.assertEqual("user_1", runtime_state.data["owner_user_id"])
        self.assertEqual("qr-content", runtime_state.data["qrcode"])
        self.assertEqual("token_1", runtime_state.data["bot_token"])
        self.assertEqual("https://node.example.test", runtime_state.data["base_url"])
        self.assertEqual("user:user_1", started["state_key"])
        self.assertIs(store, started["store"])
        self.assertEqual("qr-content", started["qrcode"])

    def test_weixin_clawbot_user_qrcode_timeout_returns_504(self):
        from langchain_api.api.routers.channels import create_channels_router

        app = FastAPI()
        app.include_router(
            create_channels_router(
                store=ChannelStore("sqlite:///:memory:"),
                weixin_client=TimeoutWeixinClient(),
            )
        )
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/channels/weixin-clawbot/users/user_1/qrcode")

        self.assertEqual(504, response.status_code)
        self.assertEqual(
            "Weixin ClawBot request timed out. Please try again.",
            response.json()["detail"],
        )

    def test_weixin_clawbot_user_status_uses_local_runtime_when_connected(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
            data={
                "owner_user_id": "user_1",
                "qrcode": "qr_1",
                "qrcode_url": "https://liteapp.weixin.qq.com/q/test?qrcode=qr_1",
                "bot_token": "token_1",
                "base_url": "https://node.example.test",
            },
        )
        app = FastAPI()
        app.include_router(
            create_channels_router(store=store, weixin_client=TimeoutWeixinClient())
        )
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/channels/weixin-clawbot/users/user_1/qrcode/status")

        self.assertEqual(200, response.status_code)
        self.assertEqual("confirmed", response.json()["status"])
        self.assertEqual("token_1", response.json()["bot_token"])
        self.assertEqual("https://node.example.test", response.json()["base_url"])

    def test_weixin_clawbot_user_management_lists_and_deletes_bound_users(self):
        from langchain_api.api.routers.channels import create_channels_router

        store = ChannelStore("sqlite:///:memory:")
        store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="user:user_1",
            data={
                "owner_user_id": "user_1",
                "bot_token": "token_1",
                "qrcode": "qr_1",
                "qrcode_url": "https://example.test/qr_1.png",
                "base_url": "https://node.example.test",
            },
        )
        store.upsert_runtime_state(
            channel="weixin_clawbot",
            state_key="default",
            data={"bot_token": "legacy_token"},
        )
        stopped = {}

        async def fake_stop_runtime(state_key):
            stopped["state_key"] = state_key

        app = FastAPI()
        app.include_router(create_channels_router(store=store))
        client = TestClient(app)

        with patch(
            "langchain_api.api.routers.channels.stop_weixin_clawbot_runtime",
            fake_stop_runtime,
        ):
            list_response = client.get("/api/channels/weixin-clawbot/users")
            delete_response = client.delete(
                "/api/channels/weixin-clawbot/users/user_1"
            )

        self.assertEqual(200, list_response.status_code)
        self.assertEqual(1, list_response.json()["total"])
        self.assertEqual("user_1", list_response.json()["items"][0]["user_id"])
        self.assertTrue(list_response.json()["items"][0]["connected"])
        self.assertEqual("token...n_1", list_response.json()["items"][0]["bot_token"])
        self.assertEqual(200, delete_response.status_code)
        self.assertEqual({"user_id": "user_1", "deleted": True}, delete_response.json())
        self.assertEqual("user:user_1", stopped["state_key"])
        self.assertIsNone(
            store.get_runtime_state(
                channel="weixin_clawbot",
                state_key="user:user_1",
            )
        )


if __name__ == "__main__":
    unittest.main()
