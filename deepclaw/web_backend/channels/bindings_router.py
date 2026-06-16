from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import is_admin, manager_user_id_from_actor
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


def create_channel_bindings_router(
    *,
    store: ChannelStore | None = None,
) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()

    @router.get("/bindings")
    async def list_bindings(
        scope: Literal["my", "all"] = "my",
        channel: str | None = None,
        owner_user_id: str | None = None,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        if scope == "all" and not is_admin(actor):
            raise HTTPException(status_code=403, detail="只有管理员可以查看全量绑定。")

        items = [
            binding.model_dump()
            for binding in await channel_store.list_bindings(
                channel=channel,
                owner_user_id=owner_user_id,
                participant_user_id=(
                    None
                    if scope == "all" and is_admin(actor)
                    else manager_user_id_from_actor(actor)
                ),
            )
        ]
        return {"items": items, "total": len(items)}

    return router
