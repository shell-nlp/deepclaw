from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import httpx
from pydantic import BaseModel

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import (
    ensure_binding_access,
    ensure_binding_owner_or_manager_match,
    ensure_runtime_state_access,
    manager_user_id_from_actor,
)
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
    WeixinClawBotAdapter,
)
from deepclaw.web_backend.channels.weixin_clawbot.client import (
    WeixinClawBotClient,
    WeixinClawBotRequestError,
    WeixinClawBotRequestTimeoutError,
)
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import (
    start_weixin_binding_runtime,
    start_weixin_clawbot_runtime,
    stop_weixin_binding_runtime,
    stop_weixin_clawbot_runtime,
)
from deepclaw.web_backend.channels.weixin_clawbot.runtime import (
    weixin_binding_state_key,
)
from deepclaw.web_backend.channels.weixin_clawbot.schemas import (
    WeixinClawBotBoundUserDeleteResponse,
    WeixinClawBotBoundUserList,
    WeixinClawBotBoundUserRead,
    WeixinClawBotPollRequest,
    WeixinClawBotQRCodeRequest,
)
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    mask_token,
    runtime_state_manager_user_id,
    weixin_clawbot_user_id_from_state_key,
    weixin_clawbot_user_state_key,
)


class WeixinBindingCreateRequest(BaseModel):
    owner_user_id: str
    display_name: str


def _binding_response(binding, *, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = binding.model_dump()
    payload["qrcode"] = (binding.runtime_state or {}).get("qrcode")
    payload["qrcode_url"] = (binding.runtime_state or {}).get("qrcode_url")
    if raw is not None:
        payload["raw"] = raw
    return payload


async def _refresh_weixin_binding_qrcode(
    *,
    binding,
    actor: CurrentActor,
    channel_store: ChannelStore,
    client: WeixinClawBotClient,
) -> dict[str, Any]:
    saved_bot_token = (binding.credentials or {}).get("bot_token")
    data = await _call_weixin_clawbot_api(
        client.fetch_login_qrcode(
            local_token_list=[str(saved_bot_token)] if saved_bot_token else []
        )
    )
    qrcode = data.get("qrcode")
    qrcode_url = data.get("qrcode_img_content") or qrcode
    updated = channel_store.update_binding(
        binding.id,
        runtime_state={
            "status": "pending",
            "qrcode": qrcode,
            "qrcode_url": qrcode_url,
        },
    )
    channel_store.upsert_runtime_state(
        channel=WEIXIN_CLAWBOT_CHANNEL,
        state_key=weixin_binding_state_key(binding.id),
        data={
            "binding_id": binding.id,
            "owner_user_id": binding.owner_user_id,
            "manager_user_id": manager_user_id_from_actor(actor),
            "qrcode": qrcode,
            "qrcode_url": qrcode_url,
            "bot_token": saved_bot_token,
            "base_url": (binding.credentials or {}).get("base_url"),
        },
    )
    return _binding_response(updated, raw=data)


async def _call_weixin_clawbot_api(
    awaitable: Awaitable[dict[str, Any]]
) -> dict[str, Any]:
    try:
        return await awaitable
    except WeixinClawBotRequestTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Weixin ClawBot request timed out. Please try again.",
        ) from exc
    except WeixinClawBotRequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Weixin ClawBot request failed. Please check the upstream service.",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Weixin ClawBot request timed out. Please try again.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Weixin ClawBot request failed. Please check the upstream service.",
        ) from exc


def create_weixin_clawbot_router(
    *,
    store: ChannelStore | None = None,
    service: ChannelService | None = None,
    weixin_client: WeixinClawBotClient | None = None,
) -> APIRouter:
    router = APIRouter(tags=["channels"])
    channel_store = store or get_channel_store()
    channel_service = service or ChannelService(store=channel_store)

    @router.post("/weixin-clawbot/qrcode")
    async def weixin_clawbot_qrcode(request: WeixinClawBotQRCodeRequest):
        client = weixin_client or WeixinClawBotClient()
        data = await _call_weixin_clawbot_api(
            client.fetch_login_qrcode(local_token_list=request.local_token_list)
        )
        return {
            "qrcode": data.get("qrcode"),
            "qrcode_url": data.get("qrcode_img_content") or data.get("qrcode"),
            "raw": data,
        }

    @router.get("/weixin-clawbot/qrcode/status")
    async def weixin_clawbot_qrcode_status(
        qrcode: str,
        verify_code: str | None = None,
    ):
        client = weixin_client or WeixinClawBotClient()
        return await _call_weixin_clawbot_api(
            client.get_qrcode_status(
                qrcode=qrcode,
                verify_code=verify_code,
            )
        )

    @router.post("/weixin-clawbot/bindings")
    async def create_weixin_binding(
        request: WeixinBindingCreateRequest,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        ensure_binding_owner_or_manager_match(
            actor=actor,
            owner_user_id=request.owner_user_id,
        )
        client = weixin_client or WeixinClawBotClient()
        binding = channel_store.create_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=request.owner_user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=request.display_name,
            credentials={},
            runtime_state={"status": "pending"},
        )
        response = await _refresh_weixin_binding_qrcode(
            binding=binding,
            actor=actor,
            channel_store=channel_store,
            client=client,
        )
        await start_weixin_binding_runtime(binding_id=binding.id, store=channel_store)
        return response

    @router.post("/weixin-clawbot/bindings/{binding_id}/qrcode")
    async def refresh_weixin_binding_qrcode(
        binding_id: int,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        binding = channel_store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Weixin ClawBot binding not found",
        )
        client = weixin_client or WeixinClawBotClient()
        await stop_weixin_binding_runtime(binding_id)
        response = await _refresh_weixin_binding_qrcode(
            binding=binding,
            actor=actor,
            channel_store=channel_store,
            client=client,
        )
        await start_weixin_binding_runtime(binding_id=binding_id, store=channel_store)
        return response

    @router.get("/weixin-clawbot/bindings/{binding_id}/qrcode/status")
    async def get_weixin_binding_qrcode_status(
        binding_id: int,
        verify_code: str | None = None,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        binding = channel_store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Weixin ClawBot binding not found",
        )
        state_key = weixin_binding_state_key(binding_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        state_data = dict(runtime_state.data or {}) if runtime_state is not None else {}
        state_data.setdefault("qrcode", (binding.runtime_state or {}).get("qrcode"))
        state_data.setdefault("qrcode_url", (binding.runtime_state or {}).get("qrcode_url"))
        state_data.setdefault("bot_token", (binding.credentials or {}).get("bot_token"))
        state_data.setdefault("base_url", (binding.credentials or {}).get("base_url"))
        if state_data.get("bot_token"):
            base_url = str(state_data.get("base_url") or "").rstrip("/")
            return {
                "status": "confirmed",
                "bot_token": str(state_data["bot_token"]),
                "baseurl": base_url,
                "base_url": base_url,
                "qrcode": state_data.get("qrcode"),
                "qrcode_url": state_data.get("qrcode_url"),
            }

        login_qrcode = state_data.get("qrcode")
        if not login_qrcode:
            raise HTTPException(status_code=404, detail="Weixin ClawBot qrcode not found")

        client = weixin_client or WeixinClawBotClient()
        status = await _call_weixin_clawbot_api(
            client.get_qrcode_status(
                qrcode=str(login_qrcode),
                verify_code=verify_code,
            )
        )
        update_data = {
            "binding_id": binding_id,
            "owner_user_id": binding.owner_user_id,
            "manager_user_id": binding.manager_user_id,
            "qrcode": login_qrcode,
            "qrcode_url": state_data.get("qrcode_url"),
        }
        if status.get("bot_token"):
            update_data["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            update_data["base_url"] = str(status["baseurl"]).rstrip("/")
        channel_store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data=update_data,
        )
        credentials: dict[str, str] = {}
        binding_runtime_state = {
            "qrcode": login_qrcode,
            "qrcode_url": state_data.get("qrcode_url"),
        }
        if status.get("bot_token"):
            credentials["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            base_url = str(status["baseurl"]).rstrip("/")
            credentials["base_url"] = base_url
            binding_runtime_state["base_url"] = base_url
        channel_store.update_binding(
            binding_id,
            credentials=credentials,
            runtime_state=binding_runtime_state,
            status="active" if status.get("bot_token") else "pending",
        )
        if status.get("bot_token"):
            await start_weixin_binding_runtime(binding_id=binding_id, store=channel_store)
        return status

    @router.delete("/weixin-clawbot/bindings/{binding_id}")
    async def delete_weixin_binding(
        binding_id: int,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        binding = channel_store.get_binding(binding_id)
        ensure_binding_access(
            actor=actor,
            binding=binding,
            not_found_detail="Weixin ClawBot binding not found",
        )
        await stop_weixin_binding_runtime(binding_id)
        channel_store.delete_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=weixin_binding_state_key(binding_id),
        )
        deleted = channel_store.delete_binding(binding_id)
        return {"binding_id": binding_id, "deleted": deleted}

    @router.post("/weixin-clawbot/users/{user_id}/qrcode")
    async def weixin_clawbot_user_qrcode(
        user_id: str,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        ensure_binding_owner_or_manager_match(actor=actor, owner_user_id=user_id)
        client = weixin_client or WeixinClawBotClient()
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        if runtime_state is not None:
            ensure_runtime_state_access(
                actor=actor,
                state_key=state_key,
                state_data=runtime_state.data or {},
            )
        saved_bot_token = (
            runtime_state.data.get("bot_token")
            if runtime_state is not None and runtime_state.data
            else None
        )
        data = await _call_weixin_clawbot_api(
            client.fetch_login_qrcode(
                local_token_list=[str(saved_bot_token)] if saved_bot_token else []
            )
        )
        qrcode = data.get("qrcode")
        qrcode_url = data.get("qrcode_img_content") or qrcode
        channel_store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data={
                "owner_user_id": user_id,
                "manager_user_id": manager_user_id_from_actor(actor),
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        channel_store.upsert_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=f"Weixin ClawBot {user_id}",
            runtime_state={
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
            },
        )
        return {
            "qrcode": qrcode,
            "qrcode_url": qrcode_url,
            "raw": data,
        }

    @router.get("/weixin-clawbot/users/{user_id}/qrcode/status")
    async def weixin_clawbot_user_qrcode_status(
        user_id: str,
        qrcode: str | None = None,
        verify_code: str | None = None,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        state_data = runtime_state.data if runtime_state is not None else {}
        if runtime_state is not None:
            ensure_runtime_state_access(
                actor=actor,
                state_key=state_key,
                state_data=state_data,
            )
        if state_data.get("bot_token"):
            base_url = str(state_data.get("base_url") or "").rstrip("/")
            return {
                "status": "confirmed",
                "bot_token": str(state_data["bot_token"]),
                "baseurl": base_url,
                "base_url": base_url,
                "qrcode": state_data.get("qrcode"),
                "qrcode_url": state_data.get("qrcode_url"),
            }

        login_qrcode = qrcode or state_data.get("qrcode")
        if not login_qrcode:
            raise HTTPException(status_code=404, detail="Weixin ClawBot qrcode not found")

        client = weixin_client or WeixinClawBotClient()
        status = await _call_weixin_clawbot_api(
            client.get_qrcode_status(
                qrcode=str(login_qrcode),
                verify_code=verify_code,
            )
        )
        update_data = {
            "owner_user_id": user_id,
            "manager_user_id": manager_user_id_from_actor(actor),
            "qrcode": login_qrcode,
        }
        if status.get("bot_token"):
            update_data["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            update_data["base_url"] = str(status["baseurl"]).rstrip("/")
        channel_store.upsert_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
            data=update_data,
        )
        binding_runtime_state = {
            "qrcode": login_qrcode,
        }
        credentials: dict[str, str] = {}
        if status.get("bot_token"):
            credentials["bot_token"] = str(status["bot_token"])
        if status.get("baseurl"):
            base_url = str(status["baseurl"]).rstrip("/")
            credentials["base_url"] = base_url
            binding_runtime_state["base_url"] = base_url
        channel_store.upsert_binding(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            owner_user_id=user_id,
            manager_user_id=manager_user_id_from_actor(actor),
            display_name=f"Weixin ClawBot {user_id}",
            credentials=credentials,
            runtime_state=binding_runtime_state,
        )
        if status.get("bot_token"):
            await start_weixin_clawbot_runtime(
                state_key=state_key,
                store=channel_store,
                qrcode=str(login_qrcode),
            )
        return status

    @router.get(
        "/weixin-clawbot/users",
        response_model=WeixinClawBotBoundUserList,
    )
    async def list_weixin_clawbot_users(
        actor: CurrentActor = Depends(get_current_actor),
    ):
        states = channel_store.list_runtime_states(channel=WEIXIN_CLAWBOT_CHANNEL)
        items: list[WeixinClawBotBoundUserRead] = []
        current_manager_user_id: str | None = None
        if not actor.is_guest and actor.role == "admin":
            current_manager_user_id = None
        else:
            current_manager_user_id = manager_user_id_from_actor(actor)
        for state in states:
            state_user_id = weixin_clawbot_user_id_from_state_key(state.state_key)
            if state_user_id is None:
                continue

            state_data = state.data or {}
            if (
                current_manager_user_id is not None
                and runtime_state_manager_user_id(state_data, state.state_key)
                != current_manager_user_id
            ):
                continue
            user_id = str(state_data.get("owner_user_id") or state_user_id)
            bot_token = state_data.get("bot_token")
            connected = bool(bot_token)
            items.append(
                WeixinClawBotBoundUserRead(
                    user_id=user_id,
                    state_key=state.state_key,
                    connected=connected,
                    status="connected" if connected else "pending",
                    bot_token=mask_token(str(bot_token)) if bot_token else None,
                    qrcode_url=state_data.get("qrcode_url"),
                    base_url=state_data.get("base_url"),
                    updated_at=state.updated_at.isoformat(),
                )
            )

        return WeixinClawBotBoundUserList(items=items, total=len(items))

    @router.delete(
        "/weixin-clawbot/users/{user_id}",
        response_model=WeixinClawBotBoundUserDeleteResponse,
    )
    async def delete_weixin_clawbot_user(
        user_id: str,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        state_key = weixin_clawbot_user_state_key(user_id)
        runtime_state = channel_store.get_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        if runtime_state is None:
            raise HTTPException(status_code=404, detail="Weixin ClawBot user not found")
        ensure_runtime_state_access(
            actor=actor,
            state_key=state_key,
            state_data=runtime_state.data or {},
        )

        await stop_weixin_clawbot_runtime(state_key)
        deleted = channel_store.delete_runtime_state(
            channel=WEIXIN_CLAWBOT_CHANNEL,
            state_key=state_key,
        )
        return WeixinClawBotBoundUserDeleteResponse(
            user_id=user_id,
            deleted=deleted,
        )

    @router.post("/weixin-clawbot/poll")
    async def weixin_clawbot_poll(
        request: WeixinClawBotPollRequest,
        background_tasks: BackgroundTasks,
    ):
        client = weixin_client or WeixinClawBotClient()
        adapter = WeixinClawBotAdapter(token=request.bot_token, client=client)
        updates = await _call_weixin_clawbot_api(
            client.get_updates(
                token=request.bot_token,
                get_updates_buf=request.get_updates_buf,
            )
        )
        messages = adapter.iter_text_messages(updates)
        for message in messages:
            background_tasks.add_task(channel_service.process_message, message, adapter)
        return {
            "status": "accepted",
            "accepted": len(messages),
            "get_updates_buf": updates.get("get_updates_buf")
            or request.get_updates_buf,
        }

    return router
