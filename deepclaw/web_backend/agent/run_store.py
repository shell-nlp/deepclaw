from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Protocol

from ag_ui.core import RunAgentInput
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, select

from deepclaw.settings import settings
from deepclaw.web_backend.db import (
    build_async_sessionmaker,
    create_async_engine_from_url,
)


def utc_now() -> datetime:
    """返回不带时区信息的 UTC 时间。

    Args:
        无。

    Returns:
        当前 UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def timestamp_from_datetime(value: datetime) -> float:
    """将数据库时间转换为 Unix 时间戳。

    Args:
        value: 数据库中的时间。

    Returns:
        Unix 时间戳。
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def datetime_from_timestamp(value: float) -> datetime:
    """将 Unix 时间戳转换为数据库时间。

    Args:
        value: Unix 时间戳。

    Returns:
        不带时区信息的 UTC 时间。
    """
    return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)


def serialize_run_input(payload: RunAgentInput) -> dict[str, Any]:
    """将 AG-UI 输入序列化为可持久化字典。

    Args:
        payload: AG-UI 标准输入。

    Returns:
        可写入 JSON 字段的字典。
    """
    return payload.model_dump(by_alias=True, exclude_none=True, mode="json")


def deserialize_run_input(payload: dict[str, Any]) -> RunAgentInput:
    """将持久化字典恢复为 AG-UI 输入。

    Args:
        payload: 持久化字典。

    Returns:
        AG-UI 标准输入。
    """
    return RunAgentInput.model_validate(payload)


@dataclass(slots=True)
class RunState:
    """可持久化的 AG-UI Run 状态。"""

    run_id: str
    thread_id: str
    input: RunAgentInput
    owner_user_id: str = "guest"
    status: str = "queued"
    last_event_id: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    error: str | None = None


class RunStore(Protocol):
    """AG-UI Run 存储抽象。"""

    async def create_run(self, state: RunState) -> bool:
        """创建 Run。

        Args:
            state: Run 状态。

        Returns:
            是否创建成功。
        """
        ...

    async def get_run(self, run_id: str, user_id: str | None = None) -> RunState | None:
        """读取 Run。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Run 状态；不存在或不属于当前用户时返回 None。
        """
        ...

    async def save_run(self, state: RunState) -> None:
        """保存 Run。

        Args:
            state: Run 状态。

        Returns:
            无。
        """
        ...

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> RunState | None:
        """更新 Run 状态。

        Args:
            run_id: Run ID。
            status: 新状态。
            error: 可选错误信息。

        Returns:
            更新后的 Run 状态；不存在时返回 None。
        """
        ...

    async def append_event(self, run_id: str, frame: str) -> int:
        """追加一个 AG-UI 事件。

        Args:
            run_id: Run ID。
            frame: EventEncoder 编码后的 AG-UI 事件。

        Returns:
            Run 内递增事件 ID。
        """
        ...

    async def get_events(self, run_id: str, after: int = 0) -> list[tuple[int, str]]:
        """读取 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。

        Returns:
            事件 ID 与编码帧列表。
        """
        ...

    def subscribe(
        self,
        run_id: str,
        after: int = 0,
        user_id: str | None = None,
    ) -> AsyncIterator[tuple[int, str]]:
        """订阅 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Run 事件异步迭代器。
        """
        ...

    async def prune_expired(self) -> int:
        """清理已过期 Run。

        Args:
            无。

        Returns:
            清理的 Run 数量。
        """
        ...

    async def close(self) -> None:
        """释放存储资源。

        Args:
            无。

        Returns:
            无。
        """
        ...


class BaseRunStore:
    """提供 Run 保留时间和清理节奏的共享实现。"""

    def __init__(
        self,
        *,
        retention_seconds: int,
        max_events_per_run: int,
        cleanup_interval_seconds: int,
    ) -> None:
        """初始化 Run 存储配置。

        Args:
            retention_seconds: Run 和事件保留秒数。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
        """
        self.retention_seconds = retention_seconds
        self.max_events_per_run = max_events_per_run
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._last_prune_at = 0.0

    def _expires_at(self, now: float | None = None) -> float:
        """计算新的过期时间。

        Args:
            now: 可选当前时间。

        Returns:
            过期 Unix 时间戳。
        """
        return (now if now is not None else time.time()) + self.retention_seconds

    def _should_prune(self) -> bool:
        """判断是否应该执行过期清理。

        Args:
            无。

        Returns:
            需要清理时返回 True。
        """
        return time.time() - self._last_prune_at >= self.cleanup_interval_seconds


class InMemoryRunStore(BaseRunStore):
    """进程内 Run 存储，供开发和无 PostgreSQL 环境回退使用。"""

    def __init__(
        self,
        *,
        retention_seconds: int = 3600,
        max_events_per_run: int = 2000,
        cleanup_interval_seconds: int = 60,
    ) -> None:
        """初始化内存 Run 存储。

        Args:
            retention_seconds: Run 和事件保留秒数。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
        """
        super().__init__(
            retention_seconds=retention_seconds,
            max_events_per_run=max_events_per_run,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )
        self._runs: dict[str, RunState] = {}
        self._events: dict[str, list[tuple[int, str]]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[tuple[int, str] | None]]] = {}
        self._lock = asyncio.Lock()

    def _prune_expired_locked(self) -> int:
        """在锁内清理过期 Run。

        Args:
            无。

        Returns:
            清理的 Run 数量。
        """
        now = time.time()
        expired = [
            run_id
            for run_id, state in self._runs.items()
            if state.expires_at > 0 and state.expires_at <= now
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)
            self._events.pop(run_id, None)
            for queue in self._subscribers.pop(run_id, set()):
                queue.put_nowait(None)
        self._last_prune_at = now
        return len(expired)

    async def _maybe_prune(self) -> None:
        """按配置节奏清理过期 Run。

        Args:
            无。

        Returns:
            无。
        """
        if self._should_prune():
            self._prune_expired_locked()

    async def create_run(self, state: RunState) -> bool:
        """创建 Run。

        Args:
            state: Run 状态。

        Returns:
            是否创建成功。
        """
        async with self._lock:
            await self._maybe_prune()
            if state.run_id in self._runs:
                return False
            now = time.time()
            state.created_at = now
            state.updated_at = now
            state.expires_at = self._expires_at(now)
            self._runs[state.run_id] = state
            self._events[state.run_id] = []
            return True

    async def get_run(self, run_id: str, user_id: str | None = None) -> RunState | None:
        """读取 Run。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Run 状态；不存在或不属于当前用户时返回 None。
        """
        async with self._lock:
            await self._maybe_prune()
            state = self._runs.get(run_id)
            if state is None or (user_id is not None and state.owner_user_id != user_id):
                return None
            return copy.deepcopy(state)

    async def save_run(self, state: RunState) -> None:
        """保存 Run。

        Args:
            state: Run 状态。

        Returns:
            无。
        """
        async with self._lock:
            await self._maybe_prune()
            state.updated_at = time.time()
            state.expires_at = self._expires_at(state.updated_at)
            self._runs[state.run_id] = copy.deepcopy(state)

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> RunState | None:
        """更新 Run 状态。

        Args:
            run_id: Run ID。
            status: 新状态。
            error: 可选错误信息。

        Returns:
            更新后的 Run 状态；不存在时返回 None。
        """
        async with self._lock:
            await self._maybe_prune()
            state = self._runs.get(run_id)
            if state is None:
                return None
            state.status = status
            state.error = error
            state.updated_at = time.time()
            state.expires_at = self._expires_at(state.updated_at)
            if status not in {"queued", "running", "cancelling"}:
                for queue in self._subscribers.get(run_id, set()):
                    queue.put_nowait(None)
            return copy.deepcopy(state)

    async def append_event(self, run_id: str, frame: str) -> int:
        """追加一个 AG-UI 事件。

        Args:
            run_id: Run ID。
            frame: EventEncoder 编码后的 AG-UI 事件。

        Returns:
            Run 内递增事件 ID。
        """
        async with self._lock:
            await self._maybe_prune()
            state = self._runs.get(run_id)
            if state is None:
                raise ValueError("Run 不存在")
            event_id = state.last_event_id + 1
            state.last_event_id = event_id
            state.updated_at = time.time()
            state.expires_at = self._expires_at(state.updated_at)
            events = self._events.setdefault(run_id, [])
            events.append((event_id, frame))
            if len(events) > self.max_events_per_run:
                del events[: len(events) - self.max_events_per_run]
            for queue in self._subscribers.get(run_id, set()):
                queue.put_nowait((event_id, frame))
            return event_id

    async def get_events(self, run_id: str, after: int = 0) -> list[tuple[int, str]]:
        """读取 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。

        Returns:
            事件 ID 与编码帧列表。
        """
        async with self._lock:
            await self._maybe_prune()
            if run_id not in self._runs:
                return []
            return [(event_id, frame) for event_id, frame in self._events.get(run_id, []) if event_id > after]

    async def subscribe(
        self,
        run_id: str,
        after: int = 0,
        user_id: str | None = None,
    ) -> AsyncIterator[tuple[int, str]]:
        """订阅 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。
            user_id: 可选当前用户 ID，用于归属校验。

        Yields:
            事件 ID 与编码帧。
        """
        async with self._lock:
            await self._maybe_prune()
            state = self._runs.get(run_id)
            if state is None or (user_id is not None and state.owner_user_id != user_id):
                raise ValueError("Run 不存在或无权访问")
            replay = [
                (event_id, frame)
                for event_id, frame in self._events.get(run_id, [])
                if event_id > after
            ]
            active = state.status in {"queued", "running", "cancelling"}
            queue: asyncio.Queue[tuple[int, str] | None] | None = None
            if active:
                queue = asyncio.Queue()
                self._subscribers.setdefault(run_id, set()).add(queue)
        try:
            for item in replay:
                yield item
            if not active or queue is None:
                return
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            if queue is not None:
                async with self._lock:
                    subscribers = self._subscribers.get(run_id)
                    if subscribers is not None:
                        subscribers.discard(queue)
                        if not subscribers:
                            self._subscribers.pop(run_id, None)

    async def prune_expired(self) -> int:
        """清理已过期 Run。

        Args:
            无。

        Returns:
            清理的 Run 数量。
        """
        async with self._lock:
            return self._prune_expired_locked()

    async def close(self) -> None:
        """释放存储资源。

        Args:
            无。

        Returns:
            无。
        """
        return None


class AgUiRunRecord(SQLModel, table=True):
    """PostgreSQL/SQLite 中的 AG-UI Run 记录。"""

    __tablename__ = "agui_runs"

    run_id: str = Field(primary_key=True)
    thread_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    input_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_event_id: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(default_factory=utc_now, index=True)
    error: str | None = None


class AgUiRunEventRecord(SQLModel, table=True):
    """PostgreSQL/SQLite 中的 AG-UI Run 事件记录。"""

    __tablename__ = "agui_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "event_id", name="uq_agui_run_event"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    event_id: int = Field(index=True)
    frame: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(default_factory=utc_now, index=True)


class SqlRunStore(BaseRunStore):
    """基于 SQLModel 的 Run 存储，当前用于 PostgreSQL。"""

    def __init__(
        self,
        db_url: str,
        *,
        retention_seconds: int = 3600,
        max_events_per_run: int = 2000,
        cleanup_interval_seconds: int = 60,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        """初始化 SQL Run 存储。

        Args:
            db_url: 数据库 URL。
            retention_seconds: Run 和事件保留秒数。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
            poll_interval_seconds: 跨进程事件订阅轮询间隔秒数。
        """
        super().__init__(
            retention_seconds=retention_seconds,
            max_events_per_run=max_events_per_run,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )
        self.db_url = db_url
        self.poll_interval_seconds = poll_interval_seconds
        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False
        self._init_lock = asyncio.Lock()

    async def _ensure_init(self) -> None:
        """确保 Run 表已经创建。

        Args:
            无。

        Returns:
            无。
        """
        if self._init_done:
            return
        async with self._init_lock:
            if self._init_done:
                return
            async with self.engine.begin() as connection:
                await connection.run_sync(SQLModel.metadata.create_all)
            self._init_done = True

    async def _maybe_prune(self) -> None:
        """按配置节奏清理过期 Run。

        Args:
            无。

        Returns:
            无。
        """
        if self._should_prune():
            await self.prune_expired()

    @staticmethod
    def _to_state(record: AgUiRunRecord) -> RunState:
        """将数据库记录转换为 Run 状态。

        Args:
            record: 数据库 Run 记录。

        Returns:
            Run 状态。
        """
        return RunState(
            run_id=record.run_id,
            thread_id=record.thread_id,
            input=deserialize_run_input(record.input_json),
            owner_user_id=record.owner_user_id,
            status=record.status,
            last_event_id=record.last_event_id,
            created_at=timestamp_from_datetime(record.created_at),
            updated_at=timestamp_from_datetime(record.updated_at),
            expires_at=timestamp_from_datetime(record.expires_at),
            error=record.error,
        )

    @staticmethod
    def _to_record(state: RunState) -> AgUiRunRecord:
        """将 Run 状态转换为数据库记录。

        Args:
            state: Run 状态。

        Returns:
            数据库 Run 记录。
        """
        return AgUiRunRecord(
            run_id=state.run_id,
            thread_id=state.thread_id,
            owner_user_id=state.owner_user_id,
            status=state.status,
            input_json=serialize_run_input(state.input),
            last_event_id=state.last_event_id,
            created_at=datetime_from_timestamp(state.created_at),
            updated_at=datetime_from_timestamp(state.updated_at),
            expires_at=datetime_from_timestamp(state.expires_at),
            error=state.error,
        )

    @staticmethod
    def _copy_record_values(record: AgUiRunRecord, state: RunState) -> None:
        """将 Run 状态字段复制到数据库记录。

        Args:
            record: 数据库 Run 记录。
            state: Run 状态。

        Returns:
            无。
        """
        record.thread_id = state.thread_id
        record.owner_user_id = state.owner_user_id
        record.status = state.status
        record.input_json = serialize_run_input(state.input)
        record.last_event_id = state.last_event_id
        record.created_at = datetime_from_timestamp(state.created_at)
        record.updated_at = datetime_from_timestamp(state.updated_at)
        record.expires_at = datetime_from_timestamp(state.expires_at)
        record.error = state.error

    async def create_run(self, state: RunState) -> bool:
        """创建 Run。

        Args:
            state: Run 状态。

        Returns:
            是否创建成功。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            existing = await session.get(AgUiRunRecord, state.run_id)
            if existing is not None:
                return False
            now = time.time()
            state.created_at = now
            state.updated_at = now
            state.expires_at = self._expires_at(now)
            session.add(self._to_record(state))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    async def get_run(self, run_id: str, user_id: str | None = None) -> RunState | None:
        """读取 Run。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Run 状态；不存在或不属于当前用户时返回 None。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiRunRecord, run_id)
            if record is None or (user_id is not None and record.owner_user_id != user_id):
                return None
            return self._to_state(record)

    async def save_run(self, state: RunState) -> None:
        """保存 Run。

        Args:
            state: Run 状态。

        Returns:
            无。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiRunRecord, state.run_id)
            if record is None:
                return
            state.updated_at = time.time()
            state.expires_at = self._expires_at(state.updated_at)
            self._copy_record_values(record, state)
            session.add(record)
            await session.commit()

    async def update_run_status(
        self,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> RunState | None:
        """更新 Run 状态。

        Args:
            run_id: Run ID。
            status: 新状态。
            error: 可选错误信息。

        Returns:
            更新后的 Run 状态；不存在时返回 None。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiRunRecord, run_id)
            if record is None:
                return None
            record.status = status
            record.error = error
            record.updated_at = utc_now()
            record.expires_at = datetime_from_timestamp(self._expires_at())
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return self._to_state(record)

    async def append_event(self, run_id: str, frame: str) -> int:
        """追加一个 AG-UI 事件。

        Args:
            run_id: Run ID。
            frame: EventEncoder 编码后的 AG-UI 事件。

        Returns:
            Run 内递增事件 ID。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiRunRecord, run_id)
            if record is None:
                raise ValueError("Run 不存在")
            event_id = record.last_event_id + 1
            record.last_event_id = event_id
            record.updated_at = utc_now()
            record.expires_at = datetime_from_timestamp(self._expires_at())
            session.add(record)
            session.add(
                AgUiRunEventRecord(
                    run_id=run_id,
                    event_id=event_id,
                    frame=frame,
                    expires_at=record.expires_at,
                )
            )
            await session.commit()
            await self._trim_events(session, run_id)
            return event_id

    async def _trim_events(self, session, run_id: str) -> None:
        """裁剪超出上限的旧事件。

        Args:
            session: 当前异步数据库会话。
            run_id: Run ID。

        Returns:
            无。
        """
        result = await session.exec(
            select(AgUiRunEventRecord)
            .where(AgUiRunEventRecord.run_id == run_id)
            .order_by(AgUiRunEventRecord.event_id.desc())
        )
        records = list(result.all())
        for record in records[self.max_events_per_run :]:
            await session.delete(record)
        await session.commit()

    async def get_events(self, run_id: str, after: int = 0) -> list[tuple[int, str]]:
        """读取 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。

        Returns:
            事件 ID 与编码帧列表。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            result = await session.exec(
                select(AgUiRunEventRecord)
                .where(
                    AgUiRunEventRecord.run_id == run_id,
                    AgUiRunEventRecord.event_id > after,
                )
                .order_by(AgUiRunEventRecord.event_id)
            )
            return [(record.event_id, record.frame) for record in result.all()]

    async def subscribe(
        self,
        run_id: str,
        after: int = 0,
        user_id: str | None = None,
    ) -> AsyncIterator[tuple[int, str]]:
        """订阅 Run 事件。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。
            user_id: 可选当前用户 ID，用于归属校验。

        Yields:
            事件 ID 与编码帧。
        """
        last_event_id = after
        while True:
            state = await self.get_run(run_id, user_id=user_id)
            if state is None:
                raise ValueError("Run 不存在或无权访问")
            events = await self.get_events(run_id, after=last_event_id)
            for event_id, frame in events:
                last_event_id = event_id
                yield event_id, frame
            if state.status not in {"queued", "running", "cancelling"}:
                await asyncio.sleep(self.poll_interval_seconds)
                events = await self.get_events(run_id, after=last_event_id)
                for event_id, frame in events:
                    last_event_id = event_id
                    yield event_id, frame
                return
            await asyncio.sleep(self.poll_interval_seconds)

    async def prune_expired(self) -> int:
        """清理已过期 Run。

        Args:
            无。

        Returns:
            清理的 Run 数量。
        """
        await self._ensure_init()
        now = utc_now()
        async with self.async_session() as session:
            run_result = await session.exec(
                select(AgUiRunRecord).where(AgUiRunRecord.expires_at <= now)
            )
            expired_runs = list(run_result.all())
            event_result = await session.exec(
                select(AgUiRunEventRecord).where(AgUiRunEventRecord.expires_at <= now)
            )
            expired_events = list(event_result.all())
            for record in expired_events:
                await session.delete(record)
            for record in expired_runs:
                await session.delete(record)
            await session.commit()
        self._last_prune_at = time.time()
        return len(expired_runs)

    async def close(self) -> None:
        """释放数据库连接资源。

        Args:
            无。

        Returns:
            无。
        """
        await self.engine.dispose()


_run_store: RunStore | None = None


def create_run_store() -> RunStore:
    """根据当前配置创建 Run 存储。

    Args:
        无。

    Returns:
        PostgreSQL Run 存储；未配置 PostgreSQL 时返回内存 Run 存储。
    """
    if settings.PG_DATABASE_URL:
        return SqlRunStore(
            settings.PG_DATABASE_URL,
            retention_seconds=settings.AGUI_RUN_RETENTION_SECONDS,
            max_events_per_run=settings.AGUI_RUN_MAX_EVENTS,
            cleanup_interval_seconds=settings.AGUI_RUN_CLEANUP_INTERVAL_SECONDS,
            poll_interval_seconds=settings.AGUI_RUN_POLL_INTERVAL_SECONDS,
        )
    return InMemoryRunStore(
        retention_seconds=settings.AGUI_RUN_RETENTION_SECONDS,
        max_events_per_run=settings.AGUI_RUN_MAX_EVENTS,
        cleanup_interval_seconds=settings.AGUI_RUN_CLEANUP_INTERVAL_SECONDS,
    )


def get_run_store() -> RunStore:
    """获取进程级 Run 存储单例。

    Args:
        无。

    Returns:
        当前进程共享的 Run 存储。
    """
    global _run_store
    if _run_store is None:
        _run_store = create_run_store()
    return _run_store
