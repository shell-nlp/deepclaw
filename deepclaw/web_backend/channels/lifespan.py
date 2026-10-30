"""渠道共享生命周期：启动连接监管与消息恢复，退出时统一回收。"""

import asyncio
from contextlib import asynccontextmanager

from deepclaw.web_backend.channels.feishu.runtime import start_saved_feishu_runtimes, stop_feishu_runtimes
from deepclaw.web_backend.channels.recovery import recover_pending_jobs
from deepclaw.web_backend.channels.runtime_manager import get_channel_runtime_manager
from deepclaw.web_backend.channels.store import get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.lifespan import start_saved_weixin_clawbot_runtimes
from deepclaw.web_backend.channels.weixin_clawbot.settings import weixin_clawbot_settings


@asynccontextmanager
async def channel_lifespan():
    """启动共享渠道服务并在部分启动失败时清理已创建资源。

    Args:
        无。
    """
    store = get_channel_store()
    recovery_task = None
    try:
        await store._ensure_init()
        recovery_task = asyncio.create_task(recover_pending_jobs(store))
        await start_saved_feishu_runtimes(store=store)
        if weixin_clawbot_settings.WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP:
            await start_saved_weixin_clawbot_runtimes(store=store)
        yield
    finally:
        if recovery_task is not None:
            recovery_task.cancel()
            await asyncio.gather(recovery_task, return_exceptions=True)
        await stop_feishu_runtimes()
        await get_channel_runtime_manager().stop_all()
