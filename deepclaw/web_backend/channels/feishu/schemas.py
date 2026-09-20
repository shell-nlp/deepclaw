from typing import Literal

from pydantic import BaseModel

from deepclaw.web_backend.channels.feishu.settings import feishu_settings


class FeishuBindingRequest(BaseModel):
    """飞书绑定创建或更新请求。"""

    owner_user_id: str | None = None
    app_id: str
    app_secret: str
    domain: Literal["feishu", "lark"] = feishu_settings.FEISHU_DEFAULT_DOMAIN
    group_policy: Literal["mention", "open"] = feishu_settings.FEISHU_DEFAULT_GROUP_POLICY
    streaming: bool = feishu_settings.FEISHU_DEFAULT_STREAMING
    display_name: str | None = None
    react_emoji: str | None = None
    done_emoji: str | None = None
