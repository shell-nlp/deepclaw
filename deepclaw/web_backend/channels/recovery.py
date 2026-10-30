"""按持久化任务恢复渠道处理，不重新执行已完成的 Agent。"""

import asyncio
import time

from loguru import logger

from deepclaw.web_backend.channels.models import ChannelMessage
from deepclaw.web_backend.channels.service import ChannelService


async def adapter_for_message(store, message):
    """根据绑定重建适配器，不把凭据写入任务表。

    Args:
        store: 渠道存储。
        message: 待恢复消息。
    """
    binding = await store.get_binding(message.binding_id)
    if message.binding_id is not None and binding is None:
        raise ValueError("渠道绑定已删除")
    if message.channel == "feishu":
        from deepclaw.web_backend.channels.feishu.adapter import FeishuAdapter

        if binding is None:
            raise ValueError("飞书消息缺少有效绑定")
        return FeishuAdapter(binding=binding)
    if message.channel == "weixin_clawbot":
        from deepclaw.web_backend.channels.weixin_clawbot.adapter import WeixinClawBotAdapter
        from deepclaw.web_backend.channels.weixin_clawbot.client import WeixinClawBotClient

        credentials = binding.credentials if binding else {}
        if not credentials:
            state = await store.get_runtime_state(channel=message.channel, state_key=f"user:{message.user_id}")
            credentials = state.data if state else {}
        if not credentials.get("bot_token"):
            raise ValueError("微信绑定尚未连接")
        client = WeixinClawBotClient()
        if credentials.get("base_url"):
            client.base_url = credentials["base_url"]
        return WeixinClawBotAdapter(token=credentials["bot_token"], client=client)
    if message.channel == "dingtalk":
        from deepclaw.web_backend.channels.dingtalk.adapter import DingTalkAdapter

        return DingTalkAdapter()
    raise ValueError("不支持的渠道")


async def recover_pending_jobs(store, *, interval: float = 5):
    """按会话顺序恢复待处理任务，并限制不同会话的并发数。

    Args:
        store: 渠道存储。
        interval: 恢复扫描间隔秒数。
    """
    service = ChannelService(store=store)
    tasks = set()
    active_sessions = set()

    async def process(job):
        """恢复单个任务，异常不能结束后台恢复器。

        Args:
            job: 待恢复任务。
        """
        try:
            message = ChannelMessage.model_validate(job.payload)
            adapter = await adapter_for_message(store, message)
            await service.process_message(message, adapter)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("渠道任务恢复失败：{}", job.id)
            async with service.jobs.lease(f"session:{job.session_key}") as acquired:
                if acquired:
                    current = await service.jobs.get(job.id)
                    if current.delivery_status != "delivered":
                        current.next_attempt_at = time.time() + 60
                        current.error = "渠道连接尚未就绪，等待恢复"
                        if current.payload.get("binding_id") is not None and await store.get_binding(current.payload["binding_id"]) is None:
                            current.execution_status = "uncertain"
                            current.error = "渠道绑定已删除，需要人工核对"
                        await service.jobs.save(current)
        finally:
            active_sessions.discard(job.session_key)

    try:
        while True:
            try:
                pending = await service.jobs.pending()
            except Exception:
                logger.exception("渠道任务扫描暂时失败，将继续重试")
                await asyncio.sleep(interval)
                continue
            for job in pending:
                if len(tasks) >= 8:
                    break
                if job.session_key in active_sessions:
                    continue
                active_sessions.add(job.session_key)
                task = asyncio.create_task(process(job))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.sleep(interval)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
