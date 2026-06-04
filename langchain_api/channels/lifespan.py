import asyncio
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from loguru import logger

from langchain_api.channels.adapters.weixin_clawbot import (
    CHANNEL as WEIXIN_CLAWBOT_CHANNEL,
)
from langchain_api.channels.config import weixin_clawbot_settings
from langchain_api.channels.store import get_channel_store
from langchain_api.channels.weixin_startup import (
    RUNTIME_STATE_KEY as WEIXIN_CLAWBOT_RUNTIME_STATE_KEY,
    WeixinClawBotRuntime,
    fetch_startup_qrcode,
)


@asynccontextmanager
async def channel_lifespan() -> AsyncIterator[None]:
    tasks = []
    weixin_task = await _start_weixin_clawbot()
    if weixin_task is not None:
        tasks.append(weixin_task)

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


async def _start_weixin_clawbot() -> asyncio.Task | None:
    if not weixin_clawbot_settings.WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP:
        return None

    try:
        channel_store = get_channel_store()
        saved_bot_token = _get_saved_weixin_bot_token(channel_store)
        local_token_list = [saved_bot_token] if saved_bot_token else []
        qrcode = await fetch_startup_qrcode(local_token_list=local_token_list)
        if qrcode.get("qrcode_url"):
            logger.info("微信 ClawBot 登录二维码链接：\n{}", qrcode["qrcode_url"])
        else:
            logger.warning("微信 ClawBot 未返回可展示的二维码链接")

        if not (
            weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP
            and (qrcode.get("qrcode") or saved_bot_token)
        ):
            return None

        runtime = WeixinClawBotRuntime(
            qrcode=str(qrcode.get("qrcode") or ""),
            store=channel_store,
            login_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS,
            message_poll_interval_seconds=weixin_clawbot_settings.WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS,
        )
        return asyncio.create_task(runtime.run_forever())
    except Exception as exc:
        logger.warning("获取微信 ClawBot 登录二维码失败：{}", exc)
        return None


def _get_saved_weixin_bot_token(channel_store) -> str | None:
    runtime_state = channel_store.get_runtime_state(
        channel=WEIXIN_CLAWBOT_CHANNEL,
        state_key=WEIXIN_CLAWBOT_RUNTIME_STATE_KEY,
    )
    if runtime_state is None or not runtime_state.data:
        return None
    saved_bot_token = runtime_state.data.get("bot_token")
    return str(saved_bot_token) if saved_bot_token else None
