import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from langchain_api.channels.adapters.weixin_clawbot import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
)
from langchain_api.channels.config import weixin_clawbot_settings
from langchain_api.channels.store import ChannelStore, get_channel_store
from langchain_api.channels.weixin_startup import (
    WeixinClawBotRuntime,
    weixin_clawbot_user_id_from_state_key,
)


_weixin_runtime_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def channel_lifespan() -> AsyncIterator[None]:
    channel_store = get_channel_store()
    if weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP:
        await start_saved_weixin_clawbot_runtimes(store=channel_store)

    try:
        yield
    finally:
        await stop_weixin_clawbot_runtimes()


async def start_saved_weixin_clawbot_runtimes(*, store: ChannelStore) -> None:
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
    existing = _weixin_runtime_tasks.get(state_key)
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
    _weixin_runtime_tasks[state_key] = task
    return task


async def stop_weixin_clawbot_runtimes() -> None:
    tasks = list(_weixin_runtime_tasks.values())
    _weixin_runtime_tasks.clear()
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task
