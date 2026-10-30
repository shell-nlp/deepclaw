"""渠道消息编排：持久化接收、串行执行、断流恢复和可靠投递。"""

import time
from contextlib import aclosing

from fastapi import Depends

from deepclaw.web_backend.channels.adapters.base import ChannelAdapter
from deepclaw.web_backend.channels.agent_client import AgentClient, RunRecoveryError, AgentRunError
from deepclaw.web_backend.channels.delivery import DurableChannelAdapter
from deepclaw.web_backend.channels.dispatcher import ResponseDispatcher
from deepclaw.web_backend.channels.jobs import ChannelJobStore
from deepclaw.web_backend.channels.models import AgentEvent, ChannelMessage, ChannelMessageRecord
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.channels.weixin_clawbot.settings import weixin_clawbot_settings


class ChannelService:
    """通过数据库租约保护同一会话的任务执行。"""

    def __init__(self, *, store=None, agent_client=None, dispatcher=None):
        """初始化渠道编排依赖。

        Args:
            store: 渠道存储。
            agent_client: Agent 客户端。
            dispatcher: 回复分发器。
        """
        self.store = store or get_channel_store()
        self.agent_client = agent_client or AgentClient()
        self.dispatcher = dispatcher or ResponseDispatcher()
        self.jobs = ChannelJobStore(self.store)

    async def accept_message(self, message: ChannelMessage):
        """确认入站前持久化消息，使进程重启后可以恢复。

        Args:
            message: 规范化消息。
        """
        return await self.jobs.enqueue(message)

    async def process_message(self, message: ChannelMessage, adapter: ChannelAdapter) -> ChannelMessageRecord:
        """领取消息并串行执行；已执行成功的任务只补发结果。

        Args:
            message: 规范化消息。
            adapter: 当前渠道适配器。
        """
        job = await self.accept_message(message)
        async with self.jobs.lease(f"session:{job.session_key}") as acquired:
            if acquired:
                job = await self.jobs.get(job.id)
                if job.delivery_status not in {"delivered", "uncertain"} and await self.jobs.is_first(job):
                    await self._process_job(job, message, adapter)
        status = "done" if job.delivery_status == "delivered" else "failed" if job.error else "processing"
        return ChannelMessageRecord(channel=message.channel, message_id=message.message_id,
                                    channel_conversation_id=message.channel_conversation_id,
                                    channel_user_id=message.channel_user_id, status=status, error=job.error)

    async def _process_job(self, job, message, adapter) -> None:
        """执行任务并分开保存执行状态与投递状态。

        Args:
            job: 已持有租约的任务。
            message: 原始规范化消息。
            adapter: 真实渠道适配器。
        """
        if job.execution_status in {"failed", "uncertain"}:
            return
        if job.delivery_status == "sending" and not job.reply_id and not hasattr(adapter, "send_message_once"):
            job.delivery_status = "uncertain"
            job.error = "上次投递结果不确定，需要人工核对"
            await self.jobs.save(job)
            return
        recover = job.execution_status == "running"
        user = await self.store.get_or_create_user(
            channel=message.channel, channel_user_id=self._routing_channel_user_id(message), user_id=message.user_id)
        channel_session = await self.store.get_or_create_session(
            channel=message.channel, channel_conversation_id=self._routing_conversation_id(message),
            channel_user_id=self._routing_channel_user_id(message), user_id=user.user_id,
            manager_user_id=message.manager_user_id or user.user_id, binding_id=message.binding_id,
            reply_mode=message.reply_mode or self._default_reply_mode(message))
        job.thread_id = job.thread_id or channel_session.session_id
        job.user_id = job.user_id or channel_session.user_id
        replay_only = job.execution_status in {"completed", "interrupted"}
        if not replay_only:
            job.execution_status = "running"
        job.attempts += 1
        job.error = None
        await self.jobs.save(job)
        delivery = DurableChannelAdapter(adapter, job, self.jobs)
        try:
            async with aclosing(self._events(job, message, replay_only, recover)) as events:
                await self.dispatcher.dispatch(
                    adapter=delivery, message=message,
                    reply_mode=message.reply_mode or channel_session.reply_mode, events=events)
            if not delivery.failed:
                job.delivery_status = "delivered"
                job.error = None
        except RunRecoveryError:
            job.execution_status = "uncertain"
            job.error = "原 Run 已不存在，需要人工核对，未重新执行"
        except AgentRunError:
            job.execution_status = "failed"
            job.error = "Agent 本次运行失败，未自动重新执行"
        except Exception:
            job.error = "Agent 执行或事件流暂不可用，将恢复原 Run"
        job.next_attempt_at = time.time() + min(2 ** min(job.attempts, 8), 300)
        await self.jobs.save(job)

    async def _events(self, job, message, replay_only: bool, recover: bool):
        """批量保存流进度，投递失败时仍持续收集 Agent 结果。

        Args:
            job: 当前任务。
            message: 规范化消息。
            replay_only: 是否仅投递已有结果。
            recover: 是否只恢复已有 Run。
        """
        if job.text:
            yield AgentEvent(event="token", data={"token": job.text})
        if replay_only:
            if job.execution_status == "interrupted":
                yield AgentEvent(event="__interrupt__")
            return
        saved_at = time.monotonic()
        stream = self.agent_client.stream(
            query=message.text, user_id=job.user_id, session_id=job.thread_id,
            run_id=job.run_id, message_id=job.id, last_event_id=job.last_event_id, recover=recover)
        async with aclosing(stream):
            async for event in stream:
                if event.event == "token" and event.data:
                    job.text += str(event.data.get("token") or "")
                elif event.event == "messages_snapshot":
                    snapshot = ResponseDispatcher._snapshot_text(event) or ""
                    if snapshot and snapshot.startswith(job.text):
                        job.text = snapshot
                elif event.event in {"run_finished", "__interrupt__"}:
                    job.execution_status = "interrupted" if event.event == "__interrupt__" else "completed"
                job.last_event_id = event.event_id or job.last_event_id
                if time.monotonic() - saved_at >= 0.5 or event.event in {"run_finished", "__interrupt__"}:
                    await self.jobs.save(job)
                    saved_at = time.monotonic()
                yield event
        if job.execution_status == "running":
            raise ConnectionError("Agent 未报告运行完成")

    def _routing_channel_user_id(self, message: ChannelMessage) -> str:
        """生成隔离后的渠道用户键。

        Args:
            message: 规范化消息。
        """
        if message.binding_id is not None:
            return f"binding:{message.binding_id}:{message.channel_user_id}"
        return f"{message.user_id}:{message.channel_user_id}" if message.user_id else message.channel_user_id

    def _routing_conversation_id(self, message: ChannelMessage) -> str:
        """生成隔离后的渠道会话键。

        Args:
            message: 规范化消息。
        """
        if message.binding_id is not None:
            return f"binding:{message.binding_id}:{message.channel_conversation_id}"
        return f"{message.user_id}:{message.channel_conversation_id}" if message.user_id else message.channel_conversation_id

    def _default_reply_mode(self, message: ChannelMessage) -> str:
        """读取渠道默认回复模式。

        Args:
            message: 规范化消息。
        """
        return weixin_clawbot_settings.WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE if message.channel == "weixin_clawbot" else "final"


def get_channel_service(store: ChannelStore = Depends(get_channel_store)) -> ChannelService:
    """创建共享数据库租约的渠道服务。

    Args:
        store: 渠道存储。
    """
    return ChannelService(store=store)
