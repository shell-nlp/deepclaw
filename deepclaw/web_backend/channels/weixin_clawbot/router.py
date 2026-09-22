from fastapi import APIRouter, BackgroundTasks, Depends

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.models import ChannelBindingDeleteResult
from deepclaw.web_backend.channels.service import ChannelService, get_channel_service
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient
from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
    WeixinClawBotBindingCreateRequest,
    WeixinClawBotBindingRead,
    WeixinClawBotPollRequest,
    WeixinClawBotPollResult,
    WeixinClawBotQRCodeStatus,
)
from deepclaw.web_backend.channels.weixin_clawbot.service import WeixinClawBotService


router = APIRouter(tags=["channels"])


def get_weixin_clawbot_client() -> WeixinClawBotClient | None:
    """返回可选的微信 ClawBot 客户端覆盖实例。"""
    return None


def get_weixin_clawbot_service(
    store: ChannelStore = Depends(get_channel_store),
    service: ChannelService = Depends(get_channel_service),
    client: WeixinClawBotClient | None = Depends(get_weixin_clawbot_client),
) -> WeixinClawBotService:
    """创建微信 ClawBot 编排服务。

    Args:
        store: 渠道存储。
        service: 共享渠道消息服务。
        client: 可选微信 ClawBot 客户端。

    Returns:
        使用当前依赖构造的微信 ClawBot 服务。
    """
    return WeixinClawBotService(store=store, service=service, client=client)


@router.post(
    "/weixin-clawbot/bindings",
    response_model=WeixinClawBotBindingRead,
    summary="创建微信 ClawBot 绑定",
    description="为当前用户创建新的微信 ClawBot 渠道绑定。",
)
async def create_weixin_binding(
    request: WeixinClawBotBindingCreateRequest,
    actor: CurrentActor = Depends(get_current_actor),
    weixin_service: WeixinClawBotService = Depends(get_weixin_clawbot_service),
):
    """创建微信 ClawBot 绑定。"""
    payload = await weixin_service.create_binding(
        actor=actor,
        owner_user_id=request.owner_user_id,
        display_name=request.display_name,
    )
    return WeixinClawBotBindingRead.model_validate(payload)


@router.post(
    "/weixin-clawbot/bindings/{binding_id}/qrcode",
    response_model=WeixinClawBotBindingRead,
    summary="刷新微信 ClawBot 绑定二维码",
    description="为指定绑定重新生成登录二维码。",
)
async def refresh_weixin_binding_qrcode(
    binding_id: int,
    actor: CurrentActor = Depends(get_current_actor),
    weixin_service: WeixinClawBotService = Depends(get_weixin_clawbot_service),
):
    """刷新指定微信 ClawBot 绑定的二维码。"""
    payload = await weixin_service.refresh_binding_qrcode(
        actor=actor,
        binding_id=binding_id,
    )
    return WeixinClawBotBindingRead.model_validate(payload)


@router.get(
    "/weixin-clawbot/bindings/{binding_id}/qrcode/status",
    response_model=WeixinClawBotQRCodeStatus,
    summary="查询微信 ClawBot 绑定二维码状态",
    description="查询指定绑定的二维码扫码和登录状态。",
)
async def get_weixin_binding_qrcode_status(
    binding_id: int,
    verify_code: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    weixin_service: WeixinClawBotService = Depends(get_weixin_clawbot_service),
):
    """查询指定微信 ClawBot 绑定的二维码状态。"""
    return WeixinClawBotQRCodeStatus.model_validate(
        await weixin_service.get_binding_qrcode_status(
            actor=actor,
            binding_id=binding_id,
            verify_code=verify_code,
        )
    )


@router.delete(
    "/weixin-clawbot/bindings/{binding_id}",
    response_model=ChannelBindingDeleteResult,
    summary="删除微信 ClawBot 绑定",
    description="删除指定微信 ClawBot 绑定及其运行态。",
)
async def delete_weixin_binding(
    binding_id: int,
    actor: CurrentActor = Depends(get_current_actor),
    weixin_service: WeixinClawBotService = Depends(get_weixin_clawbot_service),
):
    """删除指定微信 ClawBot 绑定。"""
    deleted = await weixin_service.delete_binding(actor=actor, binding_id=binding_id)
    return ChannelBindingDeleteResult(binding_id=binding_id, deleted=deleted)


@router.post(
    "/weixin-clawbot/poll",
    response_model=WeixinClawBotPollResult,
    summary="轮询微信 ClawBot 消息",
    description="主动拉取并处理微信 ClawBot 待处理消息。",
)
async def weixin_clawbot_poll(
    request: WeixinClawBotPollRequest,
    background_tasks: BackgroundTasks,
    weixin_service: WeixinClawBotService = Depends(get_weixin_clawbot_service),
):
    """轮询并处理微信 ClawBot 消息。"""
    adapter, messages, next_buf = await weixin_service.fetch_pending_messages(
        bot_token=request.bot_token,
        get_updates_buf=request.get_updates_buf,
    )
    for message in messages:
        background_tasks.add_task(weixin_service.process_message, message, adapter)
    return WeixinClawBotPollResult(
        accepted=len(messages),
        get_updates_buf=next_buf,
    )
