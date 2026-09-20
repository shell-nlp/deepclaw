from fastapi import APIRouter

from deepclaw.web_backend.channels.bindings_router import (
    router as bindings_router,
)
from deepclaw.web_backend.channels.dingtalk.router import router as dingtalk_router
from deepclaw.web_backend.channels.feishu.router import router as feishu_router
from deepclaw.web_backend.channels.session_router import router as sessions_router
from deepclaw.web_backend.channels.weixin_clawbot.router import (
    router as weixin_clawbot_router,
)


router = APIRouter(prefix="/api/channels")
router.include_router(bindings_router)
router.include_router(sessions_router)
router.include_router(feishu_router)
router.include_router(dingtalk_router)
router.include_router(weixin_clawbot_router)


def create_channels_router() -> APIRouter:
    """返回模块级渠道路由器。"""
    return router
