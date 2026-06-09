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


def get_channel_gateway_settings() -> ChannelGatewaySettings:
    return ChannelGatewaySettings()


channel_gateway_settings = get_channel_gateway_settings()
