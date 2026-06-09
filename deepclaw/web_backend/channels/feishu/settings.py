from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class FeishuSettings(BaseSettings):
    """飞书通道的全局默认值，具体凭据仍由用户 binding 提供。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    FEISHU_DEFAULT_DOMAIN: Literal["feishu", "lark"] = "feishu"
    FEISHU_DEFAULT_GROUP_POLICY: Literal["mention", "open"] = "mention"
    FEISHU_DEFAULT_STREAMING: bool = False
    FEISHU_RUNTIME_RECONNECT_SECONDS: float = 5.0


def get_feishu_settings() -> FeishuSettings:
    return FeishuSettings()


feishu_settings = get_feishu_settings()
