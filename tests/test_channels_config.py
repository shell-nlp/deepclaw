def test_channel_gateway_settings_are_separate_from_global_settings():
    from deepclaw.web_backend.channels.config import channel_gateway_settings
    from deepclaw.web_backend.channels.weixin_clawbot.settings import (
        weixin_clawbot_settings,
    )
    from deepclaw.settings import settings

    assert isinstance(channel_gateway_settings.CHANNEL_AGENT_API_URL, str)
    assert not hasattr(channel_gateway_settings, "WEIXIN_CLAWBOT_API_BASE_URL")
    assert not hasattr(channel_gateway_settings, "WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP")

    assert weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL == "https://ilinkai.weixin.qq.com"
    assert weixin_clawbot_settings.WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS == 10.0
    assert weixin_clawbot_settings.WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP is True
    assert weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP is True
    assert hasattr(settings, "GENERAL_API_VERSION")
    assert settings.GENERAL_API_VERSION in ("v1", "v2")
    assert not hasattr(settings, "CHANNEL_AGENT_API_URL")
    assert not hasattr(settings, "WEIXIN_CLAWBOT_API_BASE_URL")
    assert not hasattr(settings, "WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP")
    assert not hasattr(settings, "WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP")

