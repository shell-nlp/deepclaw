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


def create_channel_sessions_router(*, store: ChannelStore | None = None) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()

    @router.get("/sessions", response_model=ChannelSessionList)
    async def list_sessions(
        actor: CurrentActor = Depends(get_current_actor),
    ):
        sessions = [
            ChannelSessionRead.model_validate(item)
            for item in await channel_store.list_sessions()
            if is_admin(actor)
            or await session_manager_user_id(channel_store, item)
            == manager_user_id_from_actor(actor)
        ]
        return ChannelSessionList(items=sessions, total=len(sessions))

    @router.patch("/sessions/{session_id}", response_model=ChannelSessionRead)
    async def update_session(
        session_id: str,
        update: ChannelSessionUpdate,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        channel_session = await channel_store.get_session_by_session_id(session_id)
        if channel_session is None:
            raise HTTPException(status_code=404, detail="Channel session not found")
        await ensure_session_access(
            actor=actor,
            channel_store=channel_store,
            channel_session=channel_session,
        )

        if update.reply_mode is None:
            return ChannelSessionRead.model_validate(channel_session)

        try:
            channel_session = await channel_store.update_session_reply_mode(
                session_id,
                update.reply_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return ChannelSessionRead.model_validate(channel_session)

    return router
