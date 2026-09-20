from fastapi import APIRouter, BackgroundTasks, Depends

from deepclaw.web_backend.channels.dingtalk.adapter import DingTalkAdapter
from deepclaw.web_backend.channels.models import ChannelEventAccepted
from deepclaw.web_backend.channels.service import ChannelService, get_channel_service


router = APIRouter(tags=["channels"])


@router.post(
    "/dingtalk/events",
    response_model=ChannelEventAccepted,
    summary="接收钉钉事件",
    description="接收钉钉回调事件并转换为渠道消息。",
)
async def dingtalk_events(
    payload: dict,
    background_tasks: BackgroundTasks,
    service: ChannelService = Depends(get_channel_service),
):
    """接收并异步处理钉钉事件。"""
    adapter = DingTalkAdapter()
    message = await adapter.parse_event(payload)
    background_tasks.add_task(service.process_message, message, adapter)
    return ChannelEventAccepted()


def create_dingtalk_router() -> APIRouter:
    """返回模块级钉钉路由器。"""
    return router
