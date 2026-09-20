from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deepclaw.web_backend.channels.models import ChannelBindingRead


class WeixinClawBotPollRequest(BaseModel):
    """微信 ClawBot 轮询请求。"""

    bot_token: str
    get_updates_buf: str = ""


class WeixinClawBotQRCodeRequest(BaseModel):
    """微信 ClawBot 二维码生成请求。"""

    local_token_list: list[str] = Field(default_factory=list)


class WeixinClawBotBindingCreateRequest(BaseModel):
    """微信 ClawBot 绑定创建请求。"""

    owner_user_id: str
    display_name: str


class WeixinClawBotBoundUserRead(BaseModel):
    """微信 ClawBot 已绑定用户读模型。"""

    user_id: str
    state_key: str
    connected: bool
    status: str
    bot_token: str | None = None
    qrcode_url: str | None = None
    base_url: str | None = None
    updated_at: str


class WeixinClawBotBoundUserList(BaseModel):
    """微信 ClawBot 已绑定用户列表响应。"""

    items: list[WeixinClawBotBoundUserRead] = Field(default_factory=list)
    total: int


class WeixinClawBotBoundUserDeleteResponse(BaseModel):
    """微信 ClawBot 已绑定用户删除结果。"""

    user_id: str
    deleted: bool


class WeixinClawBotQRCodeRead(BaseModel):
    """微信 ClawBot 二维码响应。"""

    qrcode: str | None = None
    qrcode_url: str | None = None
    raw: dict[str, Any] | None = None


class WeixinClawBotQRCodeStatus(BaseModel):
    """微信 ClawBot 二维码状态响应，保留上游返回的额外字段。"""

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    bot_token: str | None = None
    baseurl: str | None = None
    base_url: str | None = None
    qrcode: str | None = None
    qrcode_url: str | None = None


class WeixinClawBotBindingRead(ChannelBindingRead):
    """微信 ClawBot 绑定响应。"""

    qrcode: str | None = None
    qrcode_url: str | None = None
    raw: dict[str, Any] | None = None


class WeixinClawBotPollResult(BaseModel):
    """微信 ClawBot 轮询结果。"""

    status: str = "accepted"
    accepted: int = 0
    get_updates_buf: str = ""
