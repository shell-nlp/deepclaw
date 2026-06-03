import unittest

from langchain_api.channels.weixin_startup import fetch_startup_qrcode


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

    async def get_qrcode_status(self, *, qrcode, verify_code=None):
        self.status_calls += 1
        return {"bot_token": "token_1", "baseurl": "https://node.example.test"}

    async def get_updates(self, *, token, get_updates_buf=""):
        self.update_calls += 1
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


class FakeService:
    def __init__(self):
        self.messages = []

    async def process_message(self, message, adapter):
        self.messages.append((message, adapter))


class WeixinStartupTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_startup_qrcode_prefers_qrcode_image_content(self):
        client = FakeQRCodeClient(
            {
                "qrcode": "raw_qrcode",
                "qrcode_img_content": "https://example.test/qrcode.png",
            }
        )

        result = await fetch_startup_qrcode(client=client)

        self.assertEqual("https://example.test/qrcode.png", result["qrcode_url"])
        self.assertEqual("raw_qrcode", result["qrcode"])
        self.assertEqual([], client.local_token_list)

    async def test_fetch_startup_qrcode_falls_back_to_qrcode(self):
        client = FakeQRCodeClient({"qrcode": "raw_qrcode"})

        result = await fetch_startup_qrcode(client=client)

        self.assertEqual("raw_qrcode", result["qrcode_url"])

    async def test_runtime_logs_in_then_processes_one_update_batch(self):
        from langchain_api.channels.weixin_startup import WeixinClawBotRuntime

        client = FakeRuntimeClient()
        service = FakeService()
        runtime = WeixinClawBotRuntime(
            qrcode="qr-content",
            client=client,
            service=service,
            login_poll_interval_seconds=0,
            message_poll_interval_seconds=0,
        )

        await runtime.run_once()

        self.assertEqual(1, client.status_calls)
        self.assertEqual(1, client.update_calls)
        self.assertEqual(1, len(service.messages))
        self.assertEqual("weixin_clawbot", service.messages[0][0].channel)
        self.assertEqual("hello", service.messages[0][0].text)


if __name__ == "__main__":
    unittest.main()
