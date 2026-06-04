from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


env_path = find_dotenv(filename=".env", raise_error_if_not_found=True)
load_dotenv()


class ChannelGatewaySettings(BaseSettings):
    # 渠道网关调用智能体通用接口的地址
    CHANNEL_AGENT_API_URL: str = "http://127.0.0.1:7869/api/agent/general_api"

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class WeixinClawBotSettings(BaseSettings):
    # 微信 ClawBot iLink API 地址
    WEIXIN_CLAWBOT_API_BASE_URL: str = "https://ilinkai.weixin.qq.com"

    # 服务启动时自动获取并打印微信 ClawBot 登录二维码链接
    WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP: bool = True

    # 服务启动后自动等待扫码并轮询微信 ClawBot 消息
    WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP: bool = True
    WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS: float = 2.0
    WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS: float = 1.0

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_channel_gateway_settings() -> ChannelGatewaySettings:
    return ChannelGatewaySettings()


def get_weixin_clawbot_settings() -> WeixinClawBotSettings:
    return WeixinClawBotSettings()


channel_gateway_settings = get_channel_gateway_settings()
weixin_clawbot_settings = get_weixin_clawbot_settings()
