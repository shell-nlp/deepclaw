"""渠道消息持久化任务与跨进程租约，不修改历史渠道表。"""

import asyncio
import hashlib
import json
import uuid
import time
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar

from sqlalchemy import Column, JSON
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, select, update, delete

from deepclaw.web_backend.channels.models import ChannelMessage, ChannelMessageRecord


class ChannelLeaseLostError(RuntimeError):
    """租约续期失败，旧执行必须退出后由监管器恢复。"""


_lease_context: ContextVar[tuple[str, str] | None] = ContextVar("channel_lease", default=None)


class ChannelJob(SQLModel, table=True):
    """持久化入站、Run 进度与出站投递状态。"""

    __tablename__ = "channel_jobs"
    id: str = Field(primary_key=True)
    session_key: str = Field(index=True)
    owner_user_id: str = Field(default="guest", index=True)
    manager_user_id: str = Field(default="guest", index=True)
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    run_id: str
    thread_id: str | None = None
    user_id: str | None = None
    last_event_id: str | None = None
    text: str = ""
    execution_status: str = Field(default="received", index=True)
    delivery_status: str = Field(default="pending", index=True)
    reply_id: str | None = None
    error: str | None = None
    attempts: int = 0
    next_attempt_at: float = Field(default=0, index=True)
    created_at: float
    updated_at: float
    resolved_by: str | None = None
    resolved_at: float | None = None


class ChannelLease(SQLModel, table=True):
    """数据库条件更新保护的会话与绑定租约。"""

    __tablename__ = "channel_leases"
    key: str = Field(primary_key=True)
    owner: str
    expires_at: float = Field(index=True)


async def ensure_current_lease(session) -> None:
    """在写事务内验证当前租约，阻止旧持有者覆盖新进度或连接状态。

    Args:
        session: 当前数据库写事务。
    """
    lease = _lease_context.get()
    if lease is None:
        return
    key, owner = lease
    held = (await session.exec(select(ChannelLease).where(
        ChannelLease.key == key, ChannelLease.owner == owner,
        ChannelLease.expires_at > time.time(),
    ).with_for_update())).first()
    if held is None:
        raise ChannelLeaseLostError("旧处理已失去租约，禁止覆盖新进度")


def message_key(message: ChannelMessage) -> str:
    """计算跨绑定隔离且跨进程稳定的消息标识。

    Args:
        message: 规范化渠道消息。
    """
    value = [message.channel, message.binding_id, message.user_id if message.binding_id is None else None, message.message_id]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def session_key(message: ChannelMessage) -> str:
    """计算同一渠道会话的串行执行标识。

    Args:
        message: 规范化渠道消息。
    """
    value = [message.channel, message.binding_id, message.user_id if message.binding_id is None else None,
             message.channel_conversation_id, message.channel_user_id]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


class ChannelJobStore:
    """复用渠道数据库连接，以原子操作存取任务和租约。"""

    def __init__(self, store):
        """初始化任务存储。

        Args:
            store: 渠道元数据存储。
        """
        self.store = store

    async def enqueue(self, message: ChannelMessage) -> ChannelJob:
        """持久化消息，唯一主键冲突时返回已有任务。

        Args:
            message: 规范化渠道消息。
        """
        await self.store._ensure_init()
        key = message_key(message)
        async with self.store.async_session() as session:
            existing = await session.get(ChannelJob, key)
            if existing is not None:
                return existing
            now = time.time()
            job = ChannelJob(id=key, session_key=session_key(message), payload=message.model_dump(mode="json"),
                             owner_user_id=message.user_id or "guest",
                             manager_user_id=message.manager_user_id or message.user_id or "guest",
                             run_id=str(uuid.uuid4()), created_at=now, updated_at=now)
            legacy = (await session.exec(select(ChannelMessageRecord).where(
                ChannelMessageRecord.channel == message.channel,
                ChannelMessageRecord.message_id == message.message_id,
            ))).first()
            if legacy is not None and legacy.status != "received":
                if legacy.status == "done" and message.binding_id is None:
                    job.execution_status, job.delivery_status = "completed", "delivered"
                else:
                    job.execution_status = "uncertain"
                    job.error = "历史消息缺少可恢复的 Run 信息，需要人工核对，未重新执行"
            session.add(job)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return (await session.exec(select(ChannelJob).where(ChannelJob.id == key))).one()
            await session.refresh(job)
            return job

    async def get(self, key: str) -> ChannelJob:
        """读取指定任务。

        Args:
            key: 任务主键。
        """
        async with self.store.async_session() as session:
            return (await session.exec(select(ChannelJob).where(ChannelJob.id == key))).one()

    async def save(self, job: ChannelJob) -> None:
        """保存任务进度，调用者必须持有对应会话租约。

        Args:
            job: 当前任务。
        """
        job.updated_at = time.time()
        async with self.store.async_session() as session:
            await ensure_current_lease(session)
            session.add(job)
            await session.commit()
            await session.refresh(job)

    async def pending(self, limit: int = 50) -> list[ChannelJob]:
        """按到达顺序列出待执行或待投递任务，跳过人工中断及不确定投递。

        Args:
            limit: 每次返回的任务数。
        """
        await self.store._ensure_init()
        async with self.store.async_session() as session:
            result = await session.exec(select(ChannelJob).where(
                ChannelJob.delivery_status.in_(["pending", "failed", "sending"]),
                ChannelJob.execution_status.in_(["received", "running", "completed", "interrupted"]),
                ChannelJob.next_attempt_at <= time.time(),
            ).order_by(ChannelJob.created_at, ChannelJob.id).limit(limit))
            return list(result.all())

    async def is_first(self, job: ChannelJob) -> bool:
        """检查会话内是否存在更早的未完成执行，避免后到消息抢跑。

        Args:
            job: 当前持有会话租约的任务。
        """
        async with self.store.async_session() as session:
            first = (await session.exec(select(ChannelJob).where(
                ChannelJob.session_key == job.session_key,
                ChannelJob.execution_status.in_(["received", "running", "uncertain"]),
            ).order_by(ChannelJob.created_at, ChannelJob.id).limit(1))).first()
            return first is None or first.id == job.id

    async def acquire(self, key: str, owner: str, ttl: float = 60) -> bool:
        """原子获取或续期租约，只有过期或同一持有者可以更新。

        Args:
            key: 租约标识。
            owner: 本次持有者随机标识。
            ttl: 租约有效秒数。
        """
        await self.store._ensure_init()
        now = time.time()
        async with self.store.async_session() as session:
            result = await session.exec(update(ChannelLease).where(
                ChannelLease.key == key,
                (ChannelLease.expires_at <= now) | (ChannelLease.owner == owner),
            ).values(owner=owner, expires_at=now + ttl))
            if result.rowcount:
                await session.commit()
                return True
            session.add(ChannelLease(key=key, owner=owner, expires_at=now + ttl))
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    async def release(self, key: str, owner: str) -> None:
        """仅释放仍属于当前持有者的租约。

        Args:
            key: 租约标识。
            owner: 当前持有者。
        """
        async with self.store.async_session() as session:
            await session.exec(delete(ChannelLease).where(ChannelLease.key == key, ChannelLease.owner == owner))
            await session.commit()

    @asynccontextmanager
    async def lease(self, key: str, ttl: float = 60):
        """获取并在执行期间续租，失去租约时取消执行以阻止继续发送。

        Args:
            key: 会话或绑定租约标识。
            ttl: 租约有效秒数。
        """
        owner = uuid.uuid4().hex
        acquired = await self.acquire(key, owner, ttl)
        if not acquired:
            yield False
            return
        parent = asyncio.current_task()
        lost = False

        async def heartbeat():
            """续租失败时终止受保护任务。

            Args:
                无。
            """
            nonlocal lost
            try:
                while True:
                    await asyncio.sleep(ttl / 3)
                    if not await self.acquire(key, owner, ttl):
                        lost = True
                        parent.cancel()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                lost = True
                parent.cancel()

        task = asyncio.create_task(heartbeat())
        context_token = _lease_context.set((key, owner))
        try:
            yield True
        except asyncio.CancelledError:
            if lost:
                raise ChannelLeaseLostError("渠道租约已丢失") from None
            raise
        finally:
            _lease_context.reset(context_token)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await self.release(key, owner)
