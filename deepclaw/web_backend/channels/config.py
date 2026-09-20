from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


env_path = find_dotenv(filename=".env", raise_error_if_not_found=False)
if env_path:
    load_dotenv(env_path)


class ChannelGatewaySettings(BaseSettings):
    # 可选：完整覆盖渠道调用的 Agent AG-UI Runs URL。
    # 为空时自动拼接为 http://127.0.0.1:{PORT}/api/agent/runs。
    CHANNEL_AGENT_API_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=env_path or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_channel_gateway_settings() -> ChannelGatewaySettings:
    return ChannelGatewaySettings()


channel_gateway_settings = get_channel_gateway_settings()
