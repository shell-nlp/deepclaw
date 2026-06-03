import unittest

from langchain_api.channels.models import ChannelMessage


class FakeClawBotClient:
    def __init__(self):
        self.sent = []
        self.requests = []

    async def send_message(self, *, token, to_user_id, context_token, text):
        self.sent.append(
            {
                "token": token,
                "to_user_id": to_user_id,
                "context_token": context_token,
                "text": text,
            }
        )
        return {"message_id": f"reply_{len(self.sent)}"}

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


class WeixinClawBotAdapterTest(unittest.IsolatedAsyncioTestCase):
    def sample_raw_message(self):
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

    async def test_parse_text_update_message(self):
        from langchain_api.channels.adapters.weixin_clawbot import (
            WeixinClawBotAdapter,
        )

        adapter = WeixinClawBotAdapter(client=FakeClawBotClient(), token="token_1")

        message = adapter.parse_update_message(self.sample_raw_message())

        self.assertEqual("weixin_clawbot", message.channel)
        self.assertEqual("msg_1", message.message_id)
        self.assertEqual("wx_user_1", message.channel_user_id)
        self.assertEqual("wx_user_1", message.channel_conversation_id)
        self.assertEqual("你好", message.text)
        self.assertEqual("ctx_1", message.raw["context_token"])

    async def test_send_and_edit_message_use_context_token(self):
        from langchain_api.channels.adapters.weixin_clawbot import (
            WeixinClawBotAdapter,
        )

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

        reply_id = await adapter.send_message(message, "回复")
        await adapter.edit_message(reply_id, "继续回复")

        self.assertEqual("reply_1", reply_id)
        self.assertEqual(
            [
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
            ],
            client.sent,
        )


class WeixinClawBotClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_posts_ilink_payload(self):
        from langchain_api.channels.adapters.weixin_clawbot import WeixinClawBotClient

        client = WeixinClawBotClient(request_json=FakeClawBotClient().request_json)

        await client.send_message(
            token="token_1",
            to_user_id="wx_user_1",
            context_token="ctx_1",
            text="回复",
        )

        request = client.request_json.__self__.requests[0]
        self.assertEqual("POST", request["method"])
        self.assertEqual("ilink/bot/sendmessage", request["path"])
        self.assertEqual("token_1", request["token"])
        self.assertEqual("wx_user_1", request["json_body"]["msg"]["to_user_id"])
        self.assertEqual("ctx_1", request["json_body"]["msg"]["context_token"])
        self.assertEqual(
            "回复",
            request["json_body"]["msg"]["item_list"][0]["text_item"]["text"],
        )


if __name__ == "__main__":
    unittest.main()
