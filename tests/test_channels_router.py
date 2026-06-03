import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
