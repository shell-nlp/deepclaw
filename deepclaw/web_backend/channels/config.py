from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


env_path = find_dotenv(filename=".env", raise_error_if_not_found=True)
load_dotenv()


class ChannelGatewaySettings(BaseSettings):
    # 可选：完整覆盖渠道调用的 agent general_api URL。
    # 为空时按 deepclaw.settings.GENERAL_API_VERSION 自动拼接。
    CHANNEL_AGENT_API_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=str(env_path),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_channel_gateway_settings() -> ChannelGatewaySettings:
    return ChannelGatewaySettings()


channel_gateway_settings = get_channel_gateway_settings()
