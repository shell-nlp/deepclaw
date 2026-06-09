from fastapi import APIRouter

from deepclaw.web_backend.channels.dingtalk.router import create_dingtalk_router
from deepclaw.web_backend.channels.feishu.router import create_feishu_router
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.session_router import (
    create_channel_sessions_router,
)
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient
from deepclaw.web_backend.channels.weixin_clawbot.router import (
    create_weixin_clawbot_router,
)


def create_channels_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
    weixin_client: WeixinClawBotClient | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/channels")
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    router.include_router(create_channel_sessions_router(store=channel_store))
    router.include_router(
        create_feishu_router(
            store=channel_store,
            service=channel_service,
        )
    )
    router.include_router(
        create_dingtalk_router(
            store=channel_store,
            service=channel_service,
        )
    )
    router.include_router(
        create_weixin_clawbot_router(
            store=channel_store,
            service=channel_service,
            weixin_client=weixin_client,
        )
    )
    return router
