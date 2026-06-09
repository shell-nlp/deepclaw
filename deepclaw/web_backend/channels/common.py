from typing import Any

from fastapi import HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.channels.models import ChannelBinding, ChannelSession
from deepclaw.web_backend.channels.store import ChannelStore
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    runtime_state_manager_user_id,
)


GUEST_MANAGER_USER_ID = "guest"


def is_admin(actor: CurrentActor) -> bool:
    return not actor.is_guest and actor.role == "admin"


def manager_user_id_from_actor(actor: CurrentActor) -> str:
    if actor.is_guest:
        return GUEST_MANAGER_USER_ID
    if actor.user_id:
        return actor.user_id
    raise HTTPException(status_code=403, detail="当前账号缺少可用的 user_id。")


def session_manager_user_id(
    channel_store: ChannelStore,
    channel_session: ChannelSession,
) -> str:
    manager_user_id = getattr(channel_session, "manager_user_id", None)
    if manager_user_id:
        return str(manager_user_id)

    if channel_session.channel == "weixin_clawbot":
        states = channel_store.list_runtime_states(channel="weixin_clawbot")
        for state in states:
            state_data = state.data or {}
            owner_user_id = state_data.get("owner_user_id")
            if owner_user_id and str(owner_user_id) == channel_session.user_id:
                return runtime_state_manager_user_id(state_data, state.state_key)

    return channel_session.user_id


def ensure_session_access(
    *,
    actor: CurrentActor,
    channel_store: ChannelStore,
    channel_session: ChannelSession,
) -> None:
    if is_admin(actor):
        return
    if session_manager_user_id(channel_store, channel_session) != manager_user_id_from_actor(actor):
        raise HTTPException(status_code=404, detail="Channel session not found")


def ensure_runtime_state_access(
    *,
    actor: CurrentActor,
    state_key: str,
    state_data: dict[str, Any],
) -> None:
    if is_admin(actor):
        return
    if runtime_state_manager_user_id(state_data, state_key) != manager_user_id_from_actor(actor):
        raise HTTPException(status_code=404, detail="Weixin ClawBot user not found")


def can_access_binding_as_participant(
    *,
    actor: CurrentActor,
    binding: ChannelBinding,
) -> bool:
    if is_admin(actor):
        return True
    actor_user_id = manager_user_id_from_actor(actor)
    return (
        binding.manager_user_id == actor_user_id
        or binding.owner_user_id == actor_user_id
    )


def accessible_binding_user_id(actor: CurrentActor) -> str | None:
    if is_admin(actor):
        return None
    return manager_user_id_from_actor(actor)


def filter_bindings_for_actor(
    *,
    actor: CurrentActor,
    bindings: list[ChannelBinding],
) -> list[ChannelBinding]:
    if is_admin(actor):
        return bindings
    actor_user_id = manager_user_id_from_actor(actor)
    return [
        binding
        for binding in bindings
        if binding.manager_user_id == actor_user_id
        or binding.owner_user_id == actor_user_id
    ]


def ensure_binding_owner_or_manager_match(
    *,
    actor: CurrentActor,
    owner_user_id: str,
) -> None:
    if is_admin(actor):
        return
    if actor.is_guest and owner_user_id != GUEST_MANAGER_USER_ID:
        raise HTTPException(status_code=403, detail="Guest can only bind guest-owned channels")
    if actor.is_guest:
        return
    if not owner_user_id:
        raise HTTPException(status_code=422, detail="owner_user_id is required")
    if owner_user_id == manager_user_id_from_actor(actor):
        return
    # 协作绑定模式允许代他人录入，只要后续仍由 owner 或 manager 管理。
    return


def ensure_binding_access(
    *,
    actor: CurrentActor,
    binding: ChannelBinding | None,
    not_found_detail: str = "Channel binding not found",
) -> None:
    if binding is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    if can_access_binding_as_participant(actor=actor, binding=binding):
        return
    raise HTTPException(status_code=404, detail=not_found_detail)
