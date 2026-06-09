import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from deepclaw.web_backend.channels.feishu.runtime import (
    start_saved_feishu_runtimes,
    stop_feishu_runtimes,
)
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.adapter import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
)
from deepclaw.web_backend.channels.weixin_clawbot.runtime import WeixinClawBotRuntime
from deepclaw.web_backend.channels.weixin_clawbot.runtime import (
    weixin_binding_state_key,
)
from deepclaw.web_backend.channels.weixin_clawbot.settings import (
    weixin_clawbot_settings,
)
from deepclaw.web_backend.channels.weixin_clawbot.state import (
    weixin_clawbot_user_id_from_state_key,
)


_weixin_runtime_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def channel_lifespan() -> AsyncIterator[None]:
    channel_store = get_channel_store()
    await start_saved_feishu_runtimes(store=channel_store)
    if weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP:
        await start_saved_weixin_clawbot_runtimes(store=channel_store)

    try:
        yield
    finally:
        await stop_feishu_runtimes()
        await stop_weixin_clawbot_runtimes()


async def start_saved_weixin_clawbot_runtimes(*, store: ChannelStore) -> None:
    bindings = (
        store.list_bindings(channel=WEIXIN_CLAWBOT_CHANNEL)
        if hasattr(store, "list_bindings")
        else []
    )
    if bindings:
        for binding in bindings:
            has_qrcode = bool((binding.runtime_state or {}).get("qrcode"))
            has_token = bool((binding.credentials or {}).get("bot_token"))
            if not has_qrcode and not has_token:
                continue
            await start_weixin_binding_runtime(binding_id=binding.id, store=store)
        return

    states = store.list_runtime_states(channel=WEIXIN_CLAWBOT_CHANNEL)
    for state in states:
        if not state.state_key.startswith("user:"):
            continue
        if not (state.data or {}).get("bot_token"):
            continue
        await start_weixin_clawbot_runtime(
            state_key=state.state_key,
            store=store,
            qrcode=str((state.data or {}).get("qrcode") or ""),
        )


async def start_weixin_clawbot_runtime(
    *,
    state_key: str,
    store: ChannelStore,
    qrcode: str = "",
) -> asyncio.Task | None:
    runtime_key = f"state:{state_key}"
    existing = _weixin_runtime_tasks.get(runtime_key)
    if existing is not None and not existing.done():
        return existing

    owner_user_id = weixin_clawbot_user_id_from_state_key(state_key)
    if owner_user_id is None:
        return None

    runtime = WeixinClawBotRuntime(
        qrcode=qrcode,
        store=store,
        state_key=state_key,
        owner_user_id=owner_user_id,
        login_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS,
        message_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS,
    )
    task = asyncio.create_task(runtime.run_forever())
    _weixin_runtime_tasks[runtime_key] = task
    return task


async def start_weixin_binding_runtime(
    *,
    binding_id: int,
    store: ChannelStore,
) -> asyncio.Task | None:
    binding = store.get_binding(binding_id)
    if binding is None:
        return None

    runtime_key = f"binding:{binding_id}"
    existing = _weixin_runtime_tasks.get(runtime_key)
    if existing is not None and not existing.done():
        return existing

    runtime = WeixinClawBotRuntime(
        binding_id=binding_id,
        qrcode=str((binding.runtime_state or {}).get("qrcode") or ""),
        store=store,
        state_key=weixin_binding_state_key(binding_id),
        owner_user_id=binding.owner_user_id,
        login_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS,
        message_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS,
    )
    task = asyncio.create_task(runtime.run_forever())
    _weixin_runtime_tasks[runtime_key] = task
    return task


async def stop_weixin_clawbot_runtimes() -> None:
    tasks = list(_weixin_runtime_tasks.values())
    _weixin_runtime_tasks.clear()
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


async def stop_weixin_clawbot_runtime(state_key: str) -> None:
    task = _weixin_runtime_tasks.pop(f"state:{state_key}", None)
    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def stop_weixin_binding_runtime(binding_id: int) -> None:
    task = _weixin_runtime_tasks.pop(f"binding:{binding_id}", None)
    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
