import unittest


class ChannelConfigTest(unittest.TestCase):
    def test_channel_gateway_settings_are_separate_from_global_settings(self):
        from langchain_api.channels.config import (
            channel_gateway_settings,
            weixin_clawbot_settings,
        )
        from langchain_api.settings import settings

        self.assertEqual(
            "http://127.0.0.1:7869/api/agent/general_api",
            channel_gateway_settings.CHANNEL_AGENT_API_URL,
        )
        self.assertFalse(hasattr(channel_gateway_settings, "WEIXIN_CLAWBOT_API_BASE_URL"))
        self.assertFalse(
            hasattr(channel_gateway_settings, "WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP")
        )

        self.assertEqual(
            "https://ilinkai.weixin.qq.com",
            weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL,
        )
        self.assertEqual(
            10.0,
            weixin_clawbot_settings.WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS,
        )
        self.assertTrue(weixin_clawbot_settings.WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP)
        self.assertTrue(weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP)
        self.assertFalse(hasattr(settings, "CHANNEL_AGENT_API_URL"))
        self.assertFalse(hasattr(settings, "WEIXIN_CLAWBOT_API_BASE_URL"))
        self.assertFalse(hasattr(settings, "WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP"))
        self.assertFalse(hasattr(settings, "WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP"))


if __name__ == "__main__":
    unittest.main()
