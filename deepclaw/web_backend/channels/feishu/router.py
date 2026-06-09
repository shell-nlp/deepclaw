from fastapi import APIRouter, BackgroundTasks

from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


def create_feishu_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    @router.post("/feishu/events")
    async def feishu_events(payload: dict, background_tasks: BackgroundTasks):
        adapter = FeishuAdapter()
        message = await adapter.parse_event(payload)
        background_tasks.add_task(channel_service.process_message, message, adapter)
        return {"status": "accepted"}

    return router
