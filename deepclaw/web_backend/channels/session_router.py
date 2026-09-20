from fastapi import APIRouter, Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import (
    ensure_session_access,
    is_admin,
    manager_user_id_from_actor,
    session_manager_user_id,
)
from deepclaw.web_backend.channels.models import (
    ChannelSessionList,
    ChannelSessionRead,
    ChannelSessionUpdate,
)
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


router = APIRouter(tags=["channels"])


@router.get("/sessions", response_model=ChannelSessionList, summary="查询渠道会话列表", description="返回渠道会话及其绑定、用户和最近消息信息。")
async def list_sessions(
    actor: CurrentActor = Depends(get_current_actor),
    store: ChannelStore = Depends(get_channel_store),
):
    """查询当前可见的渠道会话。"""
    sessions = [
        ChannelSessionRead.model_validate(item)
        for item in await store.list_sessions()
        if is_admin(actor)
        or await session_manager_user_id(store, item)
        == manager_user_id_from_actor(actor)
    ]
    return ChannelSessionList(items=sessions, total=len(sessions))


@router.patch("/sessions/{session_id}", response_model=ChannelSessionRead, summary="更新渠道会话", description="修改指定渠道会话的标题或状态。")
async def update_session(
    session_id: str,
    update: ChannelSessionUpdate,
    actor: CurrentActor = Depends(get_current_actor),
    store: ChannelStore = Depends(get_channel_store),
):
    """更新渠道会话回复模式。"""
    channel_session = await store.get_session_by_session_id(session_id)
    if channel_session is None:
        raise HTTPException(status_code=404, detail="Channel session not found")
    await ensure_session_access(
        actor=actor,
        channel_store=store,
        channel_session=channel_session,
    )

    if update.reply_mode is None:
        return ChannelSessionRead.model_validate(channel_session)

    try:
        channel_session = await store.update_session_reply_mode(
            session_id,
            update.reply_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ChannelSessionRead.model_validate(channel_session)


def create_channel_sessions_router() -> APIRouter:
    """返回模块级渠道会话路由器。"""
    return router
