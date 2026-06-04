import asyncio
import unittest
from unittest.mock import patch

from langchain_api.channels import lifespan as channel_lifespan_module


class ChannelLifespanTest(unittest.IsolatedAsyncioTestCase):
    async def test_channel_lifespan_starts_saved_weixin_user_runtimes_and_cancels_tasks(self):
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
                "WeixinClawBotRuntime",
                FakeRuntime,
            ),
        ):
            async with channel_lifespan_module.channel_lifespan():
                for _ in range(10):
                    if len(started) == 2:
                        break
                    await asyncio.sleep(0.01)

        self.assertEqual(2, len(cancelled))
        self.assertEqual("weixin_clawbot", captured["channel"])
        self.assertEqual(["user:user_1", "user:user_2"], [item["state_key"] for item in captured["runtimes"]])
        self.assertEqual(["user_1", "user_2"], [item["owner_user_id"] for item in captured["runtimes"]])
        self.assertTrue(all(item["store"] is fake_store for item in captured["runtimes"]))
        self.assertTrue(all(item["login_poll_interval_seconds"] == 3 for item in captured["runtimes"]))
        self.assertTrue(all(item["message_poll_interval_seconds"] == 4 for item in captured["runtimes"]))


if __name__ == "__main__":
    unittest.main()
