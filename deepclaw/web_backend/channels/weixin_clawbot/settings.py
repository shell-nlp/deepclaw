from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


env_path = find_dotenv(filename=".env", raise_error_if_not_found=True)
load_dotenv()


class WeixinClawBotSettings(BaseSettings):
    WEIXIN_CLAWBOT_API_BASE_URL: str = "https://ilinkai.weixin.qq.com"
    WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS: float = 10.0
    WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP: bool = True
    WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP: bool = True
    WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS: float = 2.0
    WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS: float = 1.0
    WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE: Literal["final", "streaming"] = "streaming"

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_weixin_clawbot_settings() -> WeixinClawBotSettings:
    return WeixinClawBotSettings()


weixin_clawbot_settings = get_weixin_clawbot_settings()
