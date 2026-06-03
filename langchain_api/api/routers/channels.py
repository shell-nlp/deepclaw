from fastapi import APIRouter, BackgroundTasks, HTTPException

from langchain_api.channels.adapters.dingtalk import DingTalkAdapter
from langchain_api.channels.adapters.feishu import FeishuAdapter
from langchain_api.channels.models import (
    ChannelSessionList,
    ChannelSessionRead,
    ChannelSessionUpdate,
)
from langchain_api.channels.service import ChannelService
from langchain_api.channels.store import ChannelStore, get_channel_store


def create_channels_router(
    *, store: ChannelStore | None = None, service: ChannelService | None = None
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
