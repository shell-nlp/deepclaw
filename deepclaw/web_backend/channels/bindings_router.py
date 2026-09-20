from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import is_admin, manager_user_id_from_actor
from deepclaw.web_backend.channels.models import ChannelBindingList, ChannelBindingRead
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


router = APIRouter(tags=["channels"])


@router.get(
    "/bindings",
    response_model=ChannelBindingList,
    summary="查询渠道绑定列表",
    description="按当前用户或管理员范围返回渠道绑定记录。",
)
async def list_bindings(
    scope: Literal["my", "all"] = "my",
    channel: str | None = None,
    owner_user_id: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    store: ChannelStore = Depends(get_channel_store),
):
    """查询当前可见的渠道绑定。"""
    if scope == "all" and not is_admin(actor):
        raise HTTPException(status_code=403, detail="只有管理员可以查看全量绑定。")

    bindings = await store.list_bindings(
        channel=channel,
        owner_user_id=owner_user_id,
        participant_user_id=(
            None
            if scope == "all" and is_admin(actor)
            else manager_user_id_from_actor(actor)
        ),
    )
    items = [ChannelBindingRead.model_validate(binding) for binding in bindings]
    return ChannelBindingList(items=items, total=len(items))


def create_channel_bindings_router() -> APIRouter:
    """返回模块级渠道绑定路由器。"""
    return router
