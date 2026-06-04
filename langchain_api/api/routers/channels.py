from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from langchain_api.channels.adapters.dingtalk import DingTalkAdapter
from langchain_api.channels.adapters.feishu import FeishuAdapter
from langchain_api.channels.adapters.weixin_clawbot import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
    WeixinClawBotAdapter,
    WeixinClawBotClient,
)
from langchain_api.channels.lifespan import start_weixin_clawbot_runtime
from langchain_api.channels.lifespan import stop_weixin_clawbot_runtime
from langchain_api.channels.models import (
    ChannelSessionList,
    ChannelSessionRead,
    ChannelSessionUpdate,
)
from langchain_api.channels.service import ChannelService
from langchain_api.channels.store import ChannelStore, get_channel_store
from langchain_api.channels.weixin_startup import weixin_clawbot_user_state_key
from langchain_api.channels.weixin_startup import weixin_clawbot_user_id_from_state_key


class WeixinClawBotPollRequest(BaseModel):
    bot_token: str
    get_updates_buf: str = ""


class WeixinClawBotQRCodeRequest(BaseModel):
    local_token_list: list[str] = []


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
    items: list[WeixinClawBotBoundUserRead]
    total: int


class WeixinClawBotBoundUserDeleteResponse(BaseModel):
    user_id: str
    deleted: bool


def _mask_token(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 5:
        return "***"
    return f"{value[:5]}...{value[-3:]}"


def create_channels_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
    weixin_client: WeixinClawBotClient | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/channels", tags=["channels"])
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    @router.post("/feishu/events")
    async def feishu_events(payload: dict, background_tasks: BackgroundTasks):
        adapter = FeishuAdapter()
        message = await adapter.parse_event(payload)
        background_tasks.add_task(channel_service.process_message, message, adapter)
        return {"status": "accepted"}

    @router.post("/dingtalk/events")
    async def dingtalk_events(payload: dict, background_tasks: BackgroundTasks):
        adapter = DingTalkAdapter()
        message = await adapter.parse_event(payload)
        background_tasks.add_task(channel_service.process_message, message, adapter)
        return {"status": "accepted"}

    @router.post("/weixin-clawbot/qrcode")
    async def weixin_clawbot_qrcode(request: WeixinClawBotQRCodeRequest):
        client = weixin_client or WeixinClawBotClient()
        data = await client.fetch_login_qrcode(
            local_token_list=request.local_token_list
        )
        return {
            "qrcode": data.get("qrcode"),
            "qrcode_url": data.get("qrcode_img_content") or data.get("qrcode"),
            "raw": data,
        }

    @router.get("/weixin-clawbot/qrcode/status")
    async def weixin_clawbot_qrcode_status(
        qrcode: str,
        verify_code: str | None = None,
    ):
        client = weixin_client or WeixinClawBotClient()
        return await client.get_qrcode_status(
            qrcode=qrcode,
            verify_code=verify_code,
        )

    @router.post("/weixin-clawbot/users/{user_id}/qrcode")
    async def weixin_clawbot_user_qrcode(user_id: str):
        client = weixin_client or WeixinClawBotClient()
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        saved_bot_token = (
            runtime_state.data.get("bot_token")
            if runtime_state is not None and runtime_state.data
            else None
        )
        data = await client.fetch_login_qrcode(
            local_token_list=[str(saved_bot_token)] if saved_bot_token else []
        )
        qrcode = data.get("qrcode")
        qrcode_url = data.get("qrcode_img_content") or qrcode
        channel_store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data={
                "owner_user_id": user_id,
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        return {
            "qrcode": qrcode,
            "qrcode_url": qrcode_url,
            "raw": data,
        }

    @router.get("/weixin-clawbot/users/{user_id}/qrcode/status")
    async def weixin_clawbot_user_qrcode_status(
        user_id: str,
        qrcode: str | None = None,
        verify_code: str | None = None,
    ):
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        state_data = runtime_state.data if runtime_state is not None else {}
        login_qrcode = qrcode or state_data.get("qrcode")
        if not login_qrcode:
            raise HTTPException(status_code=404, detail="Weixin ClawBot qrcode not found")

        client = weixin_client or WeixinClawBotClient()
        status = await client.get_qrcode_status(
            qrcode=str(login_qrcode),
            verify_code=verify_code,
        )
        update_data = {
            "owner_user_id": user_id,
            "qrcode": login_qrcode,
        }
        if status.get("bot_token"):
            update_data["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            update_data["base_url"] = str(status["baseurl"]).rstrip("/")
        channel_store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data=update_data,
        )
        if status.get("bot_token"):
            await start_weixin_clawbot_runtime(
                state_key=state_key,
                store=channel_store,
                qrcode=str(login_qrcode),
            )
        return status

    @router.get(
        "/weixin-clawbot/users",
        response_model=WeixinClawBotBoundUserList,
    )
    async def list_weixin_clawbot_users():
        states = channel_store.list_runtime_states(channel=WEIXIN_CLAWBOT_CHANNEL)
        items: list[WeixinClawBotBoundUserRead] = []
        for state in states:
            state_user_id = weixin_clawbot_user_id_from_state_key(state.state_key)
            if state_user_id is None:
                continue

            state_data = state.data or {}
            user_id = str(state_data.get("owner_user_id") or state_user_id)
            bot_token = state_data.get("bot_token")
            connected = bool(bot_token)
            items.append(
                WeixinClawBotBoundUserRead(
                    user_id=user_id,
                    state_key=state.state_key,
                    connected=connected,
                    status="connected" if connected else "pending",
                    bot_token=_mask_token(str(bot_token)) if bot_token else None,
                    qrcode_url=state_data.get("qrcode_url"),
                    base_url=state_data.get("base_url"),
                    updated_at=state.updated_at.isoformat(),
                )
            )

        return WeixinClawBotBoundUserList(items=items, total=len(items))

    @router.delete(
        "/weixin-clawbot/users/{user_id}",
        response_model=WeixinClawBotBoundUserDeleteResponse,
    )
    async def delete_weixin_clawbot_user(user_id: str):
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        if runtime_state is None:
            raise HTTPException(status_code=404, detail="Weixin ClawBot user not found")

        await stop_weixin_clawbot_runtime(state_key)
        deleted = channel_store.delete_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        return WeixinClawBotBoundUserDeleteResponse(
            user_id=user_id,
            deleted=deleted,
        )

    @router.post("/weixin-clawbot/poll")
    async def weixin_clawbot_poll(
        request: WeixinClawBotPollRequest,
        background_tasks: BackgroundTasks,
    ):
        client = weixin_client or WeixinClawBotClient()
        adapter = WeixinClawBotAdapter(token=request.bot_token, client=client)
        updates = await client.get_updates(
            token=request.bot_token,
            get_updates_buf=request.get_updates_buf,
        )
        messages = adapter.iter_text_messages(updates)
        for message in messages:
            background_tasks.add_task(channel_service.process_message, message, adapter)
        return {
            "status": "accepted",
            "accepted": len(messages),
            "get_updates_buf": updates.get("get_updates_buf")
            or request.get_updates_buf,
        }

    @router.get("/sessions", response_model=ChannelSessionList)
    async def list_sessions():
        sessions = [
            ChannelSessionRead.model_validate(item)
            for item in channel_store.list_sessions()
        ]
        return ChannelSessionList(items=sessions, total=len(sessions))

    @router.patch("/sessions/{session_id}", response_model=ChannelSessionRead)
    async def update_session(session_id: str, update: ChannelSessionUpdate):
        if update.reply_mode is None:
            channel_session = channel_store.get_session_by_session_id(session_id)
            if channel_session is None:
                raise HTTPException(status_code=404, detail="Channel session not found")
            return ChannelSessionRead.model_validate(channel_session)

        try:
            channel_session = channel_store.update_session_reply_mode(
                session_id,
                update.reply_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return ChannelSessionRead.model_validate(channel_session)

    return router
