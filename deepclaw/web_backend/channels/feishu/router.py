from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import (
    ensure_binding_access,
    ensure_binding_owner_or_manager_match,
    is_admin,
    manager_user_id_from_actor,
)
from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter
from deepclaw.web_backend.channels.feishu.runtime import (
    start_feishu_runtime,
    stop_feishu_runtime,
)
from deepclaw.web_backend.channels.feishu.settings import feishu_settings
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


class FeishuBindingRequest(BaseModel):
    owner_user_id: str | None = None
    app_id: str
    app_secret: str
    domain: Literal["feishu", "lark"] = feishu_settings.FEISHU_DEFAULT_DOMAIN
    group_policy: Literal["mention", "open"] = feishu_settings.FEISHU_DEFAULT_GROUP_POLICY
    streaming: bool = feishu_settings.FEISHU_DEFAULT_STREAMING
    display_name: str | None = None
    react_emoji: str | None = None
    done_emoji: str | None = None


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

    @router.post("/feishu/users/{user_id}/binding")
    async def upsert_feishu_binding(
        user_id: str,
        request: FeishuBindingRequest,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=user_id)
        binding = await channel_store.upsert_binding(
            channel="feishu",
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=request.display_name or f"Feishu {user_id}",
            credentials={
                "app_id": request.app_id,
                "app_secret": request.app_secret,
            },
            config={
                "domain": request.domain,
                "group_policy": request.group_policy,
                "streaming": request.streaming,
                "react_emoji": request.react_emoji,
                "done_emoji": request.done_emoji,
            },
            runtime_state={"status": "starting"},
        )
        await start_feishu_runtime(binding_id=binding.id, store=channel_store)
        return binding.model_dump()

    @router.post("/feishu/bindings")
    async def create_feishu_binding(
        request: FeishuBindingRequest,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        owner_user_id = request.owner_user_id or manager_user_id_from_actor(actor)
        ensure_binding_owner_or_manager_match(
            actor=actor,
            owner_user_id=owner_user_id,
        )
        binding = await channel_store.create_binding(
            channel="feishu",
            owner_user_id=owner_user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=request.display_name or f"Feishu {owner_user_id}",
            credentials={
                "app_id": request.app_id,
                "app_secret": request.app_secret,
            },
            config={
                "domain": request.domain,
                "group_policy": request.group_policy,
                "streaming": request.streaming,
                "react_emoji": request.react_emoji,
                "done_emoji": request.done_emoji,
            },
            runtime_state={"status": "starting"},
        )
        await start_feishu_runtime(binding_id=binding.id, store=channel_store)
        return binding.model_dump()

    @router.get("/feishu/users/{user_id}/binding")
    async def get_feishu_binding(
        user_id: str,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        bindings = await channel_store.list_bindings(channel="feishu", owner_user_id=user_id)
        binding = bindings[0] if bindings else None
        ensure_binding_access(actor=actor, binding=binding, not_found_detail="Feishu binding not found")
        return binding.model_dump()

    @router.get("/feishu/users")
    async def list_feishu_bindings(
        actor: CurrentActor = Depends(get_current_actor),
    ):
        items = [
            binding.model_dump()
            for binding in await channel_store.list_bindings(
                channel="feishu",
                participant_user_id=(
                    None if is_admin(actor) else manager_user_id_from_actor(actor)
                ),
            )
        ]
        return {"items": items, "total": len(items)}

    @router.delete("/feishu/users/{user_id}/binding")
    async def delete_feishu_binding(
        user_id: str,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        bindings = await channel_store.list_bindings(channel="feishu", owner_user_id=user_id)
        binding = bindings[0] if bindings else None
        ensure_binding_access(actor=actor, binding=binding, not_found_detail="Feishu binding not found")
        await stop_feishu_runtime(binding.id)
        deleted = await channel_store.delete_binding(binding.id)
        return {"user_id": user_id, "deleted": deleted}

    @router.delete("/feishu/bindings/{binding_id}")
    async def delete_feishu_binding_by_id(
        binding_id: int,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        binding = await channel_store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Feishu binding not found",
        )
        await stop_feishu_runtime(binding_id)
        deleted = await channel_store.delete_binding(binding_id)
        return {"binding_id": binding_id, "deleted": deleted}

    return router
