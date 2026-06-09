from pydantic import BaseModel, Field


class WeixinClawBotPollRequest(BaseModel):
    bot_token: str
    get_updates_buf: str = ""


class WeixinClawBotQRCodeRequest(BaseModel):
    local_token_list: list[str] = Field(default_factory=list)


class WeixinClawBotBoundUserRead(BaseModel):
    user_id: str
    state_key: str
    connected: bool
    status: str
    bot_token: str | None = None
    qrcode_url: str | None = None
    base_url: str | None = None
    updated_at: str


class WeixinClawBotBoundUserList(BaseModel):
    items: list[WeixinClawBotBoundUserRead] = Field(default_factory=list)
    total: int


class WeixinClawBotBoundUserDeleteResponse(BaseModel):
    user_id: str
    deleted: bool
