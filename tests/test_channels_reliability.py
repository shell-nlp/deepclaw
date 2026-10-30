"""渠道任务并发、发送失败、断流和进程重启故障测试。"""

import asyncio
import pytest


from deepclaw.web_backend.channels.jobs import ChannelJobStore, message_key
from deepclaw.web_backend.channels.models import AgentEvent, ChannelMessage
from deepclaw.web_backend.channels.service import ChannelService
from deepclaw.web_backend.channels.store import ChannelStore


class Agent:
    """记录稳定 Run 参数的假 Agent。"""

    def __init__(self):
        """初始化调用记录。

        Args:
            无。
        """
        self.calls = []

    async def stream(self, **kwargs):
        """模拟工具执行后的回复。

        Args:
            kwargs: Run 创建和恢复参数。
        """
        self.calls.append(kwargs)
        await asyncio.sleep(0.02)
        yield AgentEvent(event="token", data={"token": "完整结果"}, event_id="run:1")
        yield AgentEvent(event="run_finished", event_id="run:2")


class Adapter:
    """可模拟临时投递故障的适配器。"""

    supports_message_stream = False

    def __init__(self, fail=False):
        """初始化发送记录。

        Args:
            fail: 是否模拟发送失败。
        """
        self.fail = fail
        self.sent = []

    async def send_message_once(self, message, text, delivery_id):
        """按投递标识发送。

        Args:
            message: 入站消息。
            text: 回复正文。
            delivery_id: 固定投递标识。
        """
        self.sent.append((text, delivery_id))
        if self.fail:
            raise ConnectionError("模拟投递失败")
        return delivery_id


def message(**kwargs):
    """创建规范化消息。

    Args:
        kwargs: 消息字段覆盖。
    """
    return ChannelMessage.model_validate({"channel": "feishu", "message_id": "m1",
                                          "channel_user_id": "u", "channel_conversation_id": "c",
                                          "text": "查询", **kwargs})


def test_concurrent_duplicate_across_store_instances_runs_once(tmp_path):
    """不同服务实例并发接收同一消息只执行一次。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        stores = [ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}") for _ in range(2)]
        for store in stores:
            await store._ensure_init()
        agent, adapter = Agent(), Adapter()
        services = [ChannelService(store=store, agent_client=agent) for store in stores]
        try:
            await asyncio.gather(*(services[index % 2].process_message(message(), adapter) for index in range(12)))
            assert len(agent.calls) == 1
            assert len(adapter.sent) == 1
            assert (await services[0].jobs.get(message_key(message()))).delivery_status == "delivered"
        finally:
            for store in stores:
                await store.engine.dispose()
    asyncio.run(run())


def test_same_message_id_under_two_bindings_executes_independently(tmp_path):
    """不同绑定相同消息 ID 不相互去重。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        agent = Agent()
        service = ChannelService(store=store, agent_client=agent)
        try:
            await service.process_message(message(binding_id=1), Adapter())
            await service.process_message(message(binding_id=2), Adapter())
            assert len(agent.calls) == 2
            assert agent.calls[0]["run_id"] != agent.calls[1]["run_id"]
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_delivery_retry_after_restart_does_not_rerun_agent(tmp_path):
    """发送失败后新建服务只补发持久化结果。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        url = f"sqlite:///{tmp_path / 'channels.db'}"
        store = ChannelStore(url)
        agent, adapter = Agent(), Adapter(fail=True)
        service = ChannelService(store=store, agent_client=agent)
        await service.process_message(message(), adapter)
        job = await service.jobs.get(message_key(message()))
        assert job.execution_status == "completed"
        assert job.delivery_status == "failed"
        assert job.text == "完整结果"
        await store.engine.dispose()
        restarted = ChannelStore(url)
        retry_adapter = Adapter()
        try:
            await ChannelService(store=restarted, agent_client=agent).process_message(message(), retry_adapter)
            assert len(agent.calls) == 1
            assert retry_adapter.sent == [("完整结果", adapter.sent[0][1])]
        finally:
            await restarted.engine.dispose()
    asyncio.run(run())


def test_stream_failure_resumes_same_run_and_prefix(tmp_path):
    """断流后保留文本和游标，恢复原 Run。

    Args:
        tmp_path: 隔离数据库目录。
    """
    class BrokenAgent(Agent):
        """首次断流、随后恢复的 Agent。"""

        async def stream(self, **kwargs):
            """输出部分正文并在恢复后完成。

            Args:
                kwargs: Run 参数。
            """
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                yield AgentEvent(event="token", data={"token": "前半"}, event_id="r:1")
                raise ConnectionError("断流")
            yield AgentEvent(event="token", data={"token": "后半"}, event_id="r:2")
            yield AgentEvent(event="run_finished", event_id="r:3")

    async def run():
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        agent, adapter = BrokenAgent(), Adapter()
        service = ChannelService(store=store, agent_client=agent)
        try:
            await service.process_message(message(), adapter)
            assert not adapter.sent
            await ChannelService(store=store, agent_client=agent).process_message(message(), adapter)
            assert agent.calls[0]["run_id"] == agent.calls[1]["run_id"]
            assert agent.calls[1]["recover"] is True
            assert agent.calls[1]["last_event_id"] == "r:1"
            assert adapter.sent[0][0] == "前半后半"
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_lease_owner_cannot_release_another_owner_and_expiry_recovers(tmp_path):
    """跨实例租约互斥，过期后允许恢复且旧持有者不能删除新租约。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        jobs = ChannelJobStore(store)
        try:
            assert await jobs.acquire("session:x", "old", ttl=0)
            assert await jobs.acquire("session:x", "new")
            await jobs.release("session:x", "old")
            assert not await jobs.acquire("session:x", "third")
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_old_owner_cannot_save_after_lease_takeover(tmp_path):
    """新实例接管后，旧实例不得覆盖持久化任务进度。

    Args:
        tmp_path: 隔离数据库目录。
    """
    from sqlmodel import update
    from deepclaw.web_backend.channels.jobs import ChannelLease, ChannelLeaseLostError

    async def run():
        """强制租约过期并验证旧持有者写入被拒绝。

        Args:
            无。
        """
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        jobs = ChannelJobStore(store)
        job = await jobs.enqueue(message())
        binding = await store.create_binding(channel="feishu", owner_user_id="u", manager_user_id="u", credentials={})
        key = f"session:{job.session_key}"
        try:
            async with jobs.lease(key) as acquired:
                assert acquired
                async with store.async_session() as session:
                    await session.exec(update(ChannelLease).where(ChannelLease.key == key).values(expires_at=0))
                    await session.commit()
                assert await jobs.acquire(key, "new-owner")
                job.text = "过期持有者的结果"
                with pytest.raises(ChannelLeaseLostError):
                    await jobs.save(job)
                with pytest.raises(ChannelLeaseLostError):
                    await store.update_binding(binding.id, runtime_state={"status": "stopped"})
            assert (await jobs.get(job.id)).text == ""
            assert (await store.get_binding(binding.id)).runtime_state == {}
            assert not await jobs.acquire(key, "third-owner")
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_same_session_later_message_cannot_overtake_earlier(tmp_path):
    """先持久化但尚未执行的消息不会被后到消息抢跑。

    Args:
        tmp_path: 隔离数据库目录。
    """
    async def run():
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        agent, adapter = Agent(), Adapter()
        service = ChannelService(store=store, agent_client=agent)
        first, second = message(), message(message_id="m2")
        try:
            await service.accept_message(first)
            await service.process_message(second, adapter)
            assert not agent.calls
            await service.process_message(first, adapter)
            await service.process_message(second, adapter)
            assert [call["message_id"] for call in agent.calls] == [message_key(first), message_key(second)]
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_missing_original_run_is_quarantined_without_reexecution(tmp_path):
    """已过期 Run 标记待人工核对，并阻止后续会话消息越过它。

    Args:
        tmp_path: 隔离数据库目录。
    """
    from deepclaw.web_backend.channels.agent_client import RunRecoveryError

    class MissingAgent(Agent):
        """模拟原 Run 丢失。"""

        async def stream(self, **kwargs):
            """拒绝隐式创建新 Run。

            Args:
                kwargs: 恢复参数。
            """
            raise RunRecoveryError("丢失")
            yield

    async def run():
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        service = ChannelService(store=store, agent_client=MissingAgent())
        try:
            await service.process_message(message(), Adapter())
            job = await service.jobs.get(message_key(message()))
            assert job.execution_status == "uncertain"
            assert "未重新执行" in job.error
        finally:
            await store.engine.dispose()
    asyncio.run(run())


def test_recovery_worker_survives_temporary_database_failure(tmp_path, monkeypatch):
    """任务扫描短暂失败后恢复器继续运行，无需重启服务。

    Args:
        tmp_path: 隔离数据库目录。
        monkeypatch: 注入一次扫描故障。
    """
    from deepclaw.web_backend.channels.recovery import recover_pending_jobs

    async def run():
        """等待故障后的下一次扫描，并验证恢复任务仍存活。

        Args:
            无。
        """
        recovered = asyncio.Event()
        calls = 0

        async def pending(self, limit=50):
            """模拟数据库首次不可用，随后恢复。

            Args:
                self: 任务存储。
                limit: 查询数量上限。
            """
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("临时数据库故障")
            recovered.set()
            return []

        monkeypatch.setattr(ChannelJobStore, "pending", pending)
        store = ChannelStore(f"sqlite:///{tmp_path / 'channels.db'}")
        task = asyncio.create_task(recover_pending_jobs(store, interval=0.01))
        try:
            await asyncio.wait_for(recovered.wait(), timeout=3)
            assert not task.done()
            assert calls >= 2
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await store.engine.dispose()
    asyncio.run(run())
