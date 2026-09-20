from fastapi import APIRouter, BackgroundTasks, Depends

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.feishu.schemas import FeishuBindingRequest
from deepclaw.web_backend.channels.feishu.service import FeishuBindingService
from deepclaw.web_backend.channels.models import (
    ChannelBindingDeleteResult,
    ChannelBindingList,
    ChannelBindingRead,
    ChannelBindingUserDeleteResult,
    ChannelEventAccepted,
)
from deepclaw.web_backend.channels.service import ChannelService, get_channel_service
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


router = APIRouter(tags=["channels"])


def get_feishu_binding_service(
    store: ChannelStore = Depends(get_channel_store),
) -> FeishuBindingService:
    """创建飞书绑定服务。

    Args:
        store: 渠道存储。

    Returns:
        使用当前存储构造的飞书绑定服务。
    """
    return FeishuBindingService(store=store)


@router.post(
    "/feishu/events",
    response_model=ChannelEventAccepted,
    summary="接收飞书事件",
    description="接收飞书回调事件并转换为渠道消息。",
)
async def feishu_events(
    payload: dict,
    background_tasks: BackgroundTasks,
    service: ChannelService = Depends(get_channel_service),
):
    """接收并异步处理飞书事件。"""
    adapter = FeishuAdapter()
    message = await adapter.parse_event(payload)
    background_tasks.add_task(service.process_message, message, adapter)
    return ChannelEventAccepted()


@router.post(
    "/feishu/users/{user_id}/binding",
    response_model=ChannelBindingRead,
    summary="创建或更新飞书绑定",
    description="按用户 ID 创建或更新飞书渠道绑定。",
)
async def upsert_feishu_binding(
    user_id: str,
    request: FeishuBindingRequest,
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """按用户 ID 创建或更新飞书绑定。"""
    binding = await binding_service.upsert_binding_for_user(
        actor=actor,
        user_id=user_id,
        request=request,
    )
    return ChannelBindingRead.model_validate(binding)


@router.post(
    "/feishu/bindings",
    response_model=ChannelBindingRead,
    summary="创建飞书绑定",
    description="为当前用户创建新的飞书渠道绑定。",
)
async def create_feishu_binding(
    request: FeishuBindingRequest,
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """为当前用户创建飞书绑定。"""
    binding = await binding_service.create_binding(actor=actor, request=request)
    return ChannelBindingRead.model_validate(binding)


@router.get(
    "/feishu/users/{user_id}/binding",
    response_model=ChannelBindingRead,
    summary="获取飞书绑定",
    description="返回指定用户当前使用的飞书绑定信息。",
)
async def get_feishu_binding(
    user_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """查询指定用户的飞书绑定。"""
    binding = await binding_service.get_binding_for_user(actor=actor, user_id=user_id)
    return ChannelBindingRead.model_validate(binding)


@router.get(
    "/feishu/users",
    response_model=ChannelBindingList,
    summary="查询飞书绑定列表",
    description="返回当前用户或管理员范围内的飞书绑定。",
)
async def list_feishu_bindings(
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """查询当前可见的飞书绑定。"""
    bindings = await binding_service.list_bindings(actor=actor)
    items = [ChannelBindingRead.model_validate(binding) for binding in bindings]
    return ChannelBindingList(items=items, total=len(items))


@router.delete(
    "/feishu/users/{user_id}/binding",
    response_model=ChannelBindingUserDeleteResult,
    summary="删除飞书绑定",
    description="删除指定用户的飞书绑定及运行态信息。",
)
async def delete_feishu_binding(
    user_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """删除指定用户的飞书绑定。"""
    deleted = await binding_service.delete_binding_for_user(actor=actor, user_id=user_id)
    return ChannelBindingUserDeleteResult(user_id=user_id, deleted=deleted)


@router.delete(
    "/feishu/bindings/{binding_id}",
    response_model=ChannelBindingDeleteResult,
    summary="按 ID 删除飞书绑定",
    description="根据绑定 ID 删除飞书渠道绑定。",
)
async def delete_feishu_binding_by_id(
    binding_id: int,
    actor: CurrentActor = Depends(get_current_actor),
    binding_service: FeishuBindingService = Depends(get_feishu_binding_service),
):
    """按绑定 ID 删除飞书绑定。"""
    deleted = await binding_service.delete_binding(actor=actor, binding_id=binding_id)
    return ChannelBindingDeleteResult(binding_id=binding_id, deleted=deleted)
