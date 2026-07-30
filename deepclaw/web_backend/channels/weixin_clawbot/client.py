import base64
import random
import uuid
from collections.abc import Callable
from typing import Any, Awaitable

import httpx

from deepclaw.web_backend.channels.weixin_clawbot.settings import (
    weixin_clawbot_settings,
)


CHANNEL_VERSION = "2.4.6"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 3)
BOT_AGENT = "weixin-ClawBot-API/1.0.1 (deepclaw)"
MESSAGE_STATE_GENERATING = 1
MESSAGE_STATE_FINISH = 2
LONG_POLL_TIMEOUT_SECONDS = 35.0


RequestJson = Callable[..., Awaitable[dict[str, Any]]]


class WeixinClawBotRequestError(RuntimeError):
    pass


class WeixinClawBotRequestTimeoutError(WeixinClawBotRequestError):
    pass


def base_info() -> dict[str, str]:
    return {
        "channel_version": CHANNEL_VERSION,
        "bot_agent": BOT_AGENT,
    }


def make_headers(token: str | None = None) -> dict[str, str]:
    uin = str(random.randint(0, 0xFFFFFFFF))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class WeixinClawBotClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_json: RequestJson | None = None,
    ):
        self.base_url = (
            base_url or weixin_clawbot_settings.WEIXIN_CLAWBOT_API_BASE_URL
        ).rstrip("/")
        self.request_json = request_json or self._request_json

    async def fetch_login_qrcode(
        self, *, local_token_list: list[str] | None = None
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/get_bot_qrcode?bot_type=3",
            json_body={"local_token_list": local_token_list or []},
        )

    async def get_qrcode_status(
        self,
        *,
        qrcode: str,
        verify_code: str | None = None,
    ) -> dict[str, Any]:
        params = {"qrcode": qrcode}
        if verify_code:
            params["verify_code"] = verify_code
        return await self.request_json(
            "GET",
            "ilink/bot/get_qrcode_status",
            params=params,
        )

    async def get_updates(
        self,
        *,
        token: str,
        get_updates_buf: str = "",
    ) -> dict[str, Any]:
        try:
            return await self.request_json(
                "POST",
                "ilink/bot/getupdates",
                token=token,
                json_body={"get_updates_buf": get_updates_buf, "base_info": base_info()},
                timeout_seconds=LONG_POLL_TIMEOUT_SECONDS,
            )
        except WeixinClawBotRequestTimeoutError:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}

    async def get_config(
        self,
        *,
        token: str,
        ilink_user_id: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ilink_user_id": ilink_user_id,
            "base_info": base_info(),
        }
        if context_token:
            body["context_token"] = context_token
        return await self.request_json(
            "POST",
            "ilink/bot/getconfig",
            token=token,
            json_body=body,
        )

    async def send_typing(
        self,
        *,
        token: str,
        ilink_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> dict[str, Any]:
        return await self.request_json(
            "POST",
            "ilink/bot/sendtyping",
            token=token,
            json_body={
                "ilink_user_id": ilink_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": base_info(),
            },
        )

    async def send_message(
        self,
        *,
        token: str,
        to_user_id: str,
        context_token: str,
        text: str,
        client_id: str | None = None,
        message_state: int = MESSAGE_STATE_FINISH,
    ) -> dict[str, Any]:
        client_id = client_id or f"deepclaw-weixin-{uuid.uuid4().hex}"
        result = await self.request_json(
            "POST",
            "ilink/bot/sendmessage",
            token=token,
            json_body={
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": client_id,
                    "message_type": 2,
                    "message_state": message_state,
                    "context_token": context_token,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                },
                "base_info": base_info(),
            },
        )
        ret = result.get("ret")
        if ret is not None and ret != 0:
            raise WeixinClawBotRequestError(
                "Weixin ClawBot sendmessage failed: "
                f"ret={ret} errmsg={result.get('errmsg') or '(none)'}"
            )
        return result

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        timeout = (
            timeout_seconds
            or weixin_clawbot_settings.WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=make_headers(token),
                    json=json_body,
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise WeixinClawBotRequestTimeoutError(
                f"Weixin ClawBot request timed out for {path}"
            ) from exc
        except httpx.RequestError as exc:
            raise WeixinClawBotRequestError(
                f"Weixin ClawBot request failed for {path}"
            ) from exc
