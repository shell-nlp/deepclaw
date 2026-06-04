import asyncio
import unittest
from unittest.mock import patch

from langchain_api.channels import lifespan as channel_lifespan_module


class ChannelLifespanTest(unittest.IsolatedAsyncioTestCase):
    async def test_channel_lifespan_starts_weixin_runtime_and_cancels_task(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()
        captured = {}

        class FakeSettings:
            WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP = True
            WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP = True
            WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS = 3
            WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS = 4

        class FakeState:
            data = {"bot_token": "old_token"}

        class FakeStore:
            def get_runtime_state(self, *, channel, state_key):
                captured["channel"] = channel
                captured["state_key"] = state_key
                return FakeState()

        async def fake_fetch_startup_qrcode(*, local_token_list=None):
            captured["local_token_list"] = local_token_list
            return {"qrcode": "qr-content", "qrcode_url": "https://qr.example.test"}

        class FakeRuntime:
            def __init__(
                self,
                *,
                qrcode,
                store,
                login_poll_interval_seconds,
                message_poll_interval_seconds,
            ):
                captured["qrcode"] = qrcode
                captured["store"] = store
                captured["login_poll_interval_seconds"] = login_poll_interval_seconds
                captured["message_poll_interval_seconds"] = (
                    message_poll_interval_seconds
                )

            async def run_forever(self):
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        fake_store = FakeStore()
        with (
            patch.object(
                channel_lifespan_module,
                "weixin_clawbot_settings",
                FakeSettings(),
            ),
            patch.object(
                channel_lifespan_module,
                "get_channel_store",
                return_value=fake_store,
            ),
            patch.object(
                channel_lifespan_module,
                "fetch_startup_qrcode",
                fake_fetch_startup_qrcode,
            ),
            patch.object(
                channel_lifespan_module,
                "WeixinClawBotRuntime",
                FakeRuntime,
            ),
        ):
            async with channel_lifespan_module.channel_lifespan():
                await asyncio.wait_for(started.wait(), timeout=1)

        self.assertTrue(cancelled.is_set())
        self.assertEqual(["old_token"], captured["local_token_list"])
        self.assertEqual("qr-content", captured["qrcode"])
        self.assertIs(fake_store, captured["store"])
        self.assertEqual(3, captured["login_poll_interval_seconds"])
        self.assertEqual(4, captured["message_poll_interval_seconds"])


if __name__ == "__main__":
    unittest.main()
