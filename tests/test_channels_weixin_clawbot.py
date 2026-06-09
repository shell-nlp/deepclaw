import asyncio

from deepclaw.web_backend.channels.models import ChannelMessage


class FakeClawBotClient:
    def __init__(self):
        self.sent = []
        self.requests = []
        self.client_ids = []
        self.message_states = []

    async def send_message(
        self,
        *,
        token,
        to_user_id,
        context_token,
        text,
        client_id=None,
        message_state=2,
    ):
        self.sent.append(
            {
                "token": token,
                "to_user_id": to_user_id,
                "context_token": context_token,
                "text": text,
            }
        )
        self.client_ids.append(client_id)
        self.message_states.append(message_state)
        return {"client_id": client_id or f"reply_{len(self.sent)}"}

    async def request_json(self, method, path, *, token=None, json_body=None, params=None):
        self.requests.append(
            {
                "method": method,
                "path": path,
                "token": token,
                "json_body": json_body,
                "params": params,
            }
        )
        return {"ok": True}

    async def get_config(self, *, token, ilink_user_id, context_token=None):
        self.requests.append(
            {
                "method": "POST",
                "path": "ilink/bot/getconfig",
                "token": token,
                "json_body": {
                    "ilink_user_id": ilink_user_id,
                    "context_token": context_token,
                },
                "params": None,
            }
        )
        return {"typing_ticket": "ticket_1"}

    async def send_typing(self, *, token, ilink_user_id, typing_ticket, status):
        self.requests.append(
            {
                "method": "POST",
                "path": "ilink/bot/sendtyping",
                "token": token,
                "json_body": {
                    "ilink_user_id": ilink_user_id,
                    "typing_ticket": typing_ticket,
                    "status": status,
                },
                "params": None,
            }
        )
        return {"ok": True}


def sample_raw_message():
    return {
        "message_id": "msg_1",
        "from_user_id": {"str": "wx_user_1"},
        "context_token": "ctx_1",
        "message_item": {
            "item_list": [
                {
                    "text_item": {
                        "text": "你好",
                    }
                }
            ]
        },
    }


def test_parse_text_update_message():
    from deepclaw.web_backend.channels.weixin_clawbot.adapter import WeixinClawBotAdapter

    adapter = WeixinClawBotAdapter(client=FakeClawBotClient(), token="token_1")
    message = adapter.parse_update_message(sample_raw_message())

    assert message.channel == "weixin_clawbot"
    assert message.message_id == "msg_1"
    assert message.channel_user_id == "wx_user_1"
    assert message.channel_conversation_id == "wx_user_1"
    assert message.text == "你好"
    assert message.raw["context_token"] == "ctx_1"


def test_send_and_edit_message_use_context_token():
    from deepclaw.web_backend.channels.weixin_clawbot.adapter import WeixinClawBotAdapter

    client = FakeClawBotClient()
    adapter = WeixinClawBotAdapter(client=client, token="token_1")
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="msg_1",
        channel_user_id="wx_user_1",
        channel_conversation_id="wx_user_1",
        text="你好",
        raw={"context_token": "ctx_1"},
    )

    async def run():
        reply_id = await adapter.send_message(message, "回复")
        await adapter.edit_message(reply_id, "继续回复")
        return reply_id

    reply_id = asyncio.run(run())

    assert reply_id == "reply_1"
    assert client.sent == [
        {
            "token": "token_1",
            "to_user_id": "wx_user_1",
            "context_token": "ctx_1",
            "text": "回复",
        },
        {
            "token": "token_1",
            "to_user_id": "wx_user_1",
            "context_token": "ctx_1",
            "text": "继续回复",
        },
    ]


def test_streaming_updates_reuse_client_id_and_finish_same_message():
    from deepclaw.web_backend.channels.weixin_clawbot.adapter import WeixinClawBotAdapter

    client = FakeClawBotClient()
    adapter = WeixinClawBotAdapter(client=client, token="token_1")
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="msg_1",
        channel_user_id="wx_user_1",
        channel_conversation_id="wx_user_1",
        text="hello",
        raw={"context_token": "ctx_1"},
    )

    async def run():
        reply_id = await adapter.start_message(message, "typing")
        await adapter.edit_message(reply_id, "part one")
        await adapter.edit_message(reply_id, "part one and part two")
        await adapter.finish_message(reply_id, "part one and part two")
        return reply_id

    reply_id = asyncio.run(run())

    assert client.client_ids == [reply_id, reply_id, reply_id, reply_id]
    assert client.message_states == [1, 1, 1, 2]


def test_typing_lifecycle_uses_get_config_and_send_typing():
    from deepclaw.web_backend.channels.weixin_clawbot.adapter import WeixinClawBotAdapter

    client = FakeClawBotClient()
    adapter = WeixinClawBotAdapter(client=client, token="token_1")
    message = ChannelMessage(
        channel="weixin_clawbot",
        message_id="msg_1",
        channel_user_id="wx_user_1",
        channel_conversation_id="wx_user_1",
        text="hello",
        raw={"context_token": "ctx_1"},
    )

    async def run():
        await adapter.start_typing(message)
        await adapter.stop_typing(message)

    asyncio.run(run())

    assert [item["path"] for item in client.requests] == [
        "ilink/bot/getconfig",
        "ilink/bot/sendtyping",
        "ilink/bot/sendtyping",
    ]
    assert [item["json_body"]["status"] for item in client.requests[1:]] == [1, 2]


def test_send_message_posts_ilink_payload():
    from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient

    fake = FakeClawBotClient()
    client = WeixinClawBotClient(request_json=fake.request_json)

    asyncio.run(
        client.send_message(
            token="token_1",
            to_user_id="wx_user_1",
            context_token="ctx_1",
            text="回复",
        )
    )

    request = fake.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "ilink/bot/sendmessage"
    assert request["token"] == "token_1"
    assert request["json_body"]["msg"]["to_user_id"] == "wx_user_1"
    assert request["json_body"]["msg"]["context_token"] == "ctx_1"
    assert request["json_body"]["msg"]["item_list"][0]["text_item"]["text"] == "回复"


def test_fetch_login_qrcode_posts_local_tokens():
    from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient

    fake = FakeClawBotClient()
    client = WeixinClawBotClient(request_json=fake.request_json)

    asyncio.run(client.fetch_login_qrcode(local_token_list=["old_token"]))

    request = fake.requests[0]
    assert request["method"] == "POST"
    assert request["path"] == "ilink/bot/get_bot_qrcode?bot_type=3"
    assert request["json_body"]["local_token_list"] == ["old_token"]


def test_get_qrcode_status_uses_query_params():
    from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient

    fake = FakeClawBotClient()
    client = WeixinClawBotClient(request_json=fake.request_json)

    asyncio.run(client.get_qrcode_status(qrcode="qr-content", verify_code="1234"))

    request = fake.requests[0]
    assert request["method"] == "GET"
    assert request["path"] == "ilink/bot/get_qrcode_status"
    assert request["params"] == {"qrcode": "qr-content", "verify_code": "1234"}

