import asyncio
from deepclaw.web_backend.channels.runtime_manager import get_channel_runtime_manager
from deepclaw.web_backend.channels.store import ChannelStore
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


async def start_saved_weixin_clawbot_runtimes(*, store: ChannelStore) -> None:
    bindings = (
        await store.list_bindings(channel=WEIXIN_CLAWBOT_CHANNEL)
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

    states = await store.list_runtime_states(channel=WEIXIN_CLAWBOT_CHANNEL)
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
    runtime_key = f"weixin:state:{state_key}"

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
    return await get_channel_runtime_manager().start(runtime_key, factory=runtime.run_forever, store=store)


async def start_weixin_binding_runtime(
    *,
    binding_id: int,
    store: ChannelStore,
) -> asyncio.Task | None:
    binding = await store.get_binding(binding_id)
    if binding is None:
        return None

    runtime_key = f"weixin:binding:{binding_id}"

    runtime = WeixinClawBotRuntime(
        binding_id=binding_id,
        qrcode=str((binding.runtime_state or {}).get("qrcode") or ""),
        store=store,
        state_key=weixin_binding_state_key(binding_id),
        owner_user_id=binding.owner_user_id,
        login_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS,
        message_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS,
    )
    return await get_channel_runtime_manager().start(runtime_key, factory=runtime.run_forever, store=store)


async def stop_weixin_clawbot_runtimes() -> None:
    """停止统一管理器中的微信任务。

    Args:
        无。
    """
    await get_channel_runtime_manager().stop_prefix("weixin:")


async def stop_weixin_clawbot_runtime(state_key: str) -> None:
    """停止历史状态键对应的微信任务。

    Args:
        state_key: 历史运行状态键。
    """
    await get_channel_runtime_manager().stop(f"weixin:state:{state_key}")


async def stop_weixin_binding_runtime(binding_id: int) -> None:
    """停止指定绑定的微信任务。

    Args:
        binding_id: 绑定标识。
    """
    await get_channel_runtime_manager().stop(f"weixin:binding:{binding_id}")
