from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Protocol

from ag_ui.core import RunAgentInput
from loguru import logger
from sqlalchemy import JSON, Column, Index, UniqueConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, delete, select

from deepclaw.settings import settings
from deepclaw.web_backend.db import (
    build_async_sessionmaker,
    create_async_engine_from_url,
)


PERSISTENT_THREAD_EXPIRES_AT = datetime(9999, 12, 30)


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


def thread_expires_datetime(value: float) -> datetime:
    """将 Thread 过期时间转换为数据库值。

    Args:
        value: Thread 过期 Unix 时间戳；0 表示永不过期。

    Returns:
        数据库中的过期时间。
    """
    if value <= 0:
        return PERSISTENT_THREAD_EXPIRES_AT
    return datetime_from_timestamp(value)


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


def get_thread_title(payload: RunAgentInput) -> str | None:
    """从 AG-UI 输入提取 Thread 标题。

    Args:
        payload: AG-UI 标准输入。

    Returns:
        首条用户消息文本；没有时返回 None。
    """
    for message in payload.messages:
        role = getattr(message, "role", None)
        normalized_role = getattr(role, "value", role)
        if normalized_role not in {"user", "human"}:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()[:240]
    return None


def get_message_title(messages: list[Any]) -> str | None:
    """从 checkpoint 消息中提取 Thread 标题。

    Args:
        messages: LangGraph checkpoint 中的消息列表。

    Returns:
        首条用户消息文本；没有时返回 None。
    """
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", None)
        if role not in {"user", "human"}:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()[:240]
        if isinstance(content, list):
            text = "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
            if text:
                return text[:240]
    return None


def checkpoint_timestamp(value: Any) -> float:
    """解析 checkpoint 时间。

    Args:
        value: checkpoint 中的 ISO8601 时间值。

    Returns:
        Unix 时间戳；无法解析时返回当前时间。
    """
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return time.time()


@dataclass(slots=True)
class RunState:
    """可持久化的 AG-UI Run 状态。"""

    run_id: str
    thread_id: str
    input: RunAgentInput
    owner_user_id: str = "guest"
    agent_id: str = "agent"
    status: str = "queued"
    last_event_id: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class ThreadState:
    """可持久化的 AG-UI Thread 状态。"""

    thread_id: str
    owner_user_id: str = "guest"
    agent_id: str = "agent"
    title: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    expires_at: float = 0.0


class RunStore(Protocol):
    """AG-UI Run 存储抽象。"""

    async def create_thread(self, state: ThreadState) -> bool:
        """创建 Thread。

        Args:
            state: Thread 状态。

        Returns:
            是否创建成功。
        """
        ...

    async def get_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> ThreadState | None:
        """读取 Thread。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Thread 状态；不存在或不属于当前用户时返回 None。
        """
        ...

    async def save_thread(self, state: ThreadState) -> None:
        """保存 Thread。

        Args:
            state: Thread 状态。

        Returns:
            无。
        """
        ...

    async def list_threads(
        self,
        user_id: str,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[ThreadState]:
        """列出当前用户的 Thread。

        Args:
            user_id: 当前用户 ID。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Thread 列表。
        """
        ...

    async def delete_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> bool:
        """删除 Thread 及其关联 Run 与事件。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            是否删除成功。
        """
        ...

    async def list_runs_by_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[RunState]:
        """按 Thread 查询 Run。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Run 列表。
        """
        ...

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

    async def initialize(self) -> None:
        """初始化底层存储资源。

        Args:
            无。

        Returns:
            无。
        """
        ...


async def get_or_backfill_thread(
    store: RunStore,
    thread_id: str,
    user_id: str | None = None,
) -> ThreadState | None:
    """读取 Thread，不存在时从历史 Run 回填。

    Args:
        store: Run/Thread 存储。
        thread_id: Thread ID。
        user_id: 可选当前用户 ID，用于归属校验。

    Returns:
        Thread 状态；不存在或不属于当前用户时返回 None。
    """
    thread = await store.get_thread(thread_id, user_id=user_id)
    if thread is not None:
        return thread

    runs = await store.list_runs_by_thread(
        thread_id,
        user_id=user_id,
        limit=1,
    )
    if not runs:
        return None

    run = runs[0]
    thread = ThreadState(
        thread_id=thread_id,
        owner_user_id=run.owner_user_id,
        agent_id=run.agent_id,
        title=get_thread_title(run.input),
        created_at=run.created_at,
        updated_at=run.updated_at,
        expires_at=run.expires_at,
    )
    await store.create_thread(thread)
    return thread


class BaseRunStore:
    """提供 Run 保留时间和清理节奏的共享实现。"""

    def __init__(
        self,
        *,
        retention_seconds: int,
        thread_retention_seconds: int,
        max_events_per_run: int,
        cleanup_interval_seconds: int,
    ) -> None:
        """初始化 Run 存储配置。

        Args:
            retention_seconds: Run 和事件保留秒数。
            thread_retention_seconds: Thread 保留秒数；0 表示不自动过期。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
        """
        self.retention_seconds = retention_seconds
        self.thread_retention_seconds = thread_retention_seconds
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

    def _thread_expires_at(self, now: float | None = None) -> float:
        """计算 Thread 过期时间。

        Args:
            now: 可选当前时间。

        Returns:
            过期 Unix 时间戳；0 表示不自动过期。
        """
        if self.thread_retention_seconds <= 0:
            return 0.0
        return (now if now is not None else time.time()) + self.thread_retention_seconds

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
        thread_retention_seconds: int = 0,
        max_events_per_run: int = 2000,
        cleanup_interval_seconds: int = 60,
    ) -> None:
        """初始化内存 Run 存储。

        Args:
            retention_seconds: Run 和事件保留秒数。
            thread_retention_seconds: Thread 保留秒数；0 表示不自动过期。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
        """
        super().__init__(
            retention_seconds=retention_seconds,
            thread_retention_seconds=thread_retention_seconds,
            max_events_per_run=max_events_per_run,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )
        self._runs: dict[str, RunState] = {}
        self._threads: dict[str, ThreadState] = {}
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
        expired_threads = []
        if self.thread_retention_seconds > 0:
            expired_threads = [
                thread_id
                for thread_id, state in self._threads.items()
                if state.expires_at > 0 and state.expires_at <= now
            ]
        for thread_id in expired_threads:
            self._threads.pop(thread_id, None)
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

    def _touch_thread_locked(self, thread_id: str) -> None:
        """更新 Thread 最近活跃时间。

        Args:
            thread_id: Thread ID。

        Returns:
            无。
        """
        thread = self._threads.get(thread_id)
        if thread is None:
            return
        thread.updated_at = time.time()
        thread.expires_at = self._thread_expires_at(thread.updated_at)

    def _backfill_threads_locked(self) -> None:
        """从已有 Run 回填缺失的 Thread 记录。

        Args:
            无。

        Returns:
            无。
        """
        for run in self._runs.values():
            if run.thread_id in self._threads:
                continue
            self._threads[run.thread_id] = ThreadState(
                thread_id=run.thread_id,
                owner_user_id=run.owner_user_id,
                agent_id=run.agent_id,
                title=get_thread_title(run.input),
                created_at=run.created_at,
                updated_at=run.updated_at,
                expires_at=self._thread_expires_at(run.updated_at),
            )

    async def create_thread(self, state: ThreadState) -> bool:
        """创建 Thread。

        Args:
            state: Thread 状态。

        Returns:
            是否创建成功。
        """
        async with self._lock:
            await self._maybe_prune()
            if state.thread_id in self._threads:
                return False
            now = time.time()
            if state.created_at <= 0:
                state.created_at = now
            if state.updated_at <= 0:
                state.updated_at = state.created_at
            if state.expires_at <= 0:
                state.expires_at = self._thread_expires_at(state.updated_at)
            self._threads[state.thread_id] = copy.deepcopy(state)
            return True

    async def get_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> ThreadState | None:
        """读取 Thread。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Thread 状态；不存在或不属于当前用户时返回 None。
        """
        async with self._lock:
            await self._maybe_prune()
            state = self._threads.get(thread_id)
            if state is None or (user_id is not None and state.owner_user_id != user_id):
                return None
            return copy.deepcopy(state)

    async def save_thread(self, state: ThreadState) -> None:
        """保存 Thread。

        Args:
            state: Thread 状态。

        Returns:
            无。
        """
        async with self._lock:
            await self._maybe_prune()
            state.updated_at = time.time()
            state.expires_at = self._thread_expires_at(state.updated_at)
            self._threads[state.thread_id] = copy.deepcopy(state)

    async def list_threads(
        self,
        user_id: str,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[ThreadState]:
        """列出当前用户的 Thread。

        Args:
            user_id: 当前用户 ID。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Thread 列表。
        """
        async with self._lock:
            await self._maybe_prune()
            self._backfill_threads_locked()
            states = [
                copy.deepcopy(state)
                for state in self._threads.values()
                if state.owner_user_id == user_id
                and (agent_id is None or state.agent_id == agent_id)
            ]
        states.sort(key=lambda state: state.updated_at, reverse=True)
        return states[:limit]

    async def delete_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> bool:
        """删除 Thread 及其关联 Run 与事件。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            是否删除成功。
        """
        async with self._lock:
            await self._maybe_prune()
            thread = self._threads.get(thread_id)
            if thread is None or (user_id is not None and thread.owner_user_id != user_id):
                return False
            self._threads.pop(thread_id, None)
            run_ids = [
                run_id
                for run_id, state in self._runs.items()
                if state.thread_id == thread_id
            ]
            for run_id in run_ids:
                self._runs.pop(run_id, None)
                self._events.pop(run_id, None)
                for queue in self._subscribers.pop(run_id, set()):
                    queue.put_nowait(None)
            return True

    async def list_runs_by_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[RunState]:
        """按 Thread 查询 Run。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Run 列表。
        """
        async with self._lock:
            await self._maybe_prune()
            states = [
                copy.deepcopy(state)
                for state in self._runs.values()
                if state.thread_id == thread_id
                and (user_id is None or state.owner_user_id == user_id)
                and (agent_id is None or state.agent_id == agent_id)
            ]
        states.sort(key=lambda state: state.updated_at, reverse=True)
        return states[:limit]

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
            self._touch_thread_locked(state.thread_id)
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
            self._touch_thread_locked(state.thread_id)

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
            self._touch_thread_locked(state.thread_id)
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
            self._touch_thread_locked(state.thread_id)
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

    async def initialize(self) -> None:
        """初始化内存存储。

        Args:
            无。

        Returns:
            无。
        """
        return None


class AgUiRunRecord(SQLModel, table=True):
    """PostgreSQL/SQLite 中的 AG-UI Run 记录。"""

    __tablename__ = "agui_runs"
    __table_args__ = (
        Index("ix_agui_runs_owner_updated", "owner_user_id", "updated_at"),
        Index("ix_agui_runs_owner_agent_updated", "owner_user_id", "agent_id", "updated_at"),
    )

    run_id: str = Field(primary_key=True)
    thread_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    agent_id: str = Field(default="agent", index=True)
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


class AgUiThreadRecord(SQLModel, table=True):
    """PostgreSQL/SQLite 中的 AG-UI Thread 记录。"""

    __tablename__ = "agui_threads"
    __table_args__ = (
        Index("ix_agui_threads_owner_updated", "owner_user_id", "updated_at"),
        Index("ix_agui_threads_owner_agent_updated", "owner_user_id", "agent_id", "updated_at"),
    )

    thread_id: str = Field(primary_key=True)
    owner_user_id: str = Field(index=True)
    agent_id: str = Field(default="agent", index=True)
    title: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(default_factory=utc_now, index=True)


class AgUiCheckpointRecord(SQLModel, table=True):
    """LangGraph checkpoint 的只读映射，用于恢复 Thread 索引。"""

    __tablename__ = "checkpoints"
    __table_args__ = {"extend_existing": True}

    thread_id: str = Field(primary_key=True)
    checkpoint_ns: str = Field(primary_key=True, default="")
    checkpoint_id: str = Field(primary_key=True)
    checkpoint: dict[str, Any] = Field(sa_column=Column(JSON))


class SqlRunStore(BaseRunStore):
    """基于 SQLModel 的 Run 存储，当前用于 PostgreSQL。"""

    def __init__(
        self,
        db_url: str,
        *,
        retention_seconds: int = 3600,
        thread_retention_seconds: int = 0,
        max_events_per_run: int = 2000,
        cleanup_interval_seconds: int = 60,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        """初始化 SQL Run 存储。

        Args:
            db_url: 数据库 URL。
            retention_seconds: Run 和事件保留秒数。
            thread_retention_seconds: Thread 保留秒数；0 表示不自动过期。
            max_events_per_run: 单个 Run 最多保留的事件数。
            cleanup_interval_seconds: 过期清理最小间隔秒数。
            poll_interval_seconds: 跨进程事件订阅轮询间隔秒数。
        """
        super().__init__(
            retention_seconds=retention_seconds,
            thread_retention_seconds=thread_retention_seconds,
            max_events_per_run=max_events_per_run,
            cleanup_interval_seconds=cleanup_interval_seconds,
        )
        self.db_url = db_url
        self.poll_interval_seconds = poll_interval_seconds
        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False
        self._init_lock = asyncio.Lock()
        self._backfilled_users: set[str] = set()
        self._backfill_lock = asyncio.Lock()

    @staticmethod
    def _ensure_agent_columns_sync(connection) -> None:
        """为历史 AG-UI 表补齐 agent_id 列。

        Args:
            connection: SQLAlchemy 同步数据库连接。

        Returns:
            无。
        """
        inspector = inspect(connection)
        run_columns = {column["name"] for column in inspector.get_columns("agui_runs")}
        if "agent_id" not in run_columns:
            connection.execute(
                text(
                    "ALTER TABLE agui_runs "
                    "ADD COLUMN agent_id VARCHAR(64) NOT NULL DEFAULT 'agent'"
                )
            )
        thread_columns = {
            column["name"] for column in inspector.get_columns("agui_threads")
        }
        if "agent_id" not in thread_columns:
            connection.execute(
                text(
                    "ALTER TABLE agui_threads "
                    "ADD COLUMN agent_id VARCHAR(64) NOT NULL DEFAULT 'agent'"
                )
            )

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
                await connection.run_sync(self._ensure_agent_columns_sync)
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agui_runs_owner_updated "
                        "ON agui_runs (owner_user_id, updated_at)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agui_runs_owner_agent_updated "
                        "ON agui_runs (owner_user_id, agent_id, updated_at)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agui_threads_owner_updated "
                        "ON agui_threads (owner_user_id, updated_at)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agui_threads_owner_agent_updated "
                        "ON agui_threads (owner_user_id, agent_id, updated_at)"
                    )
                )
                await connection.execute(
                    text(
                        "UPDATE agui_runs "
                        "SET agent_id = 'rag' "
                        "WHERE agent_id = 'agent' "
                        "AND ("
                        "CAST(input_json AS TEXT) LIKE '%\"index_name\"%' "
                        "OR CAST(input_json AS TEXT) LIKE '%\"graph_name\"%'"
                        ")"
                    )
                )
                await connection.execute(
                    text(
                        "UPDATE agui_threads "
                        "SET agent_id = ("
                        "SELECT agent_id FROM agui_runs "
                        "WHERE agui_runs.thread_id = agui_threads.thread_id "
                        "ORDER BY updated_at DESC LIMIT 1"
                        ") "
                        "WHERE EXISTS ("
                        "SELECT 1 FROM agui_runs "
                        "WHERE agui_runs.thread_id = agui_threads.thread_id"
                        ")"
                    )
                )
                if self.thread_retention_seconds <= 0:
                    await connection.execute(
                        text(
                            "UPDATE agui_threads SET expires_at = :expires_at "
                            "WHERE expires_at <> :expires_at"
                        ),
                        {"expires_at": PERSISTENT_THREAD_EXPIRES_AT},
                    )
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
    def _to_thread_state(record: AgUiThreadRecord) -> ThreadState:
        """将数据库记录转换为 Thread 状态。

        Args:
            record: 数据库 Thread 记录。

        Returns:
            Thread 状态。
        """
        expires_at = record.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
        return ThreadState(
            thread_id=record.thread_id,
            owner_user_id=record.owner_user_id,
            agent_id=record.agent_id,
            title=record.title,
            created_at=timestamp_from_datetime(record.created_at),
            updated_at=timestamp_from_datetime(record.updated_at),
            expires_at=(
                0.0
                if expires_at >= PERSISTENT_THREAD_EXPIRES_AT
                else timestamp_from_datetime(expires_at)
            ),
        )

    @staticmethod
    def _to_thread_record(state: ThreadState) -> AgUiThreadRecord:
        """将 Thread 状态转换为数据库记录。

        Args:
            state: Thread 状态。

        Returns:
            数据库 Thread 记录。
        """
        return AgUiThreadRecord(
            thread_id=state.thread_id,
            owner_user_id=state.owner_user_id,
            agent_id=state.agent_id,
            title=state.title,
            created_at=datetime_from_timestamp(state.created_at),
            updated_at=datetime_from_timestamp(state.updated_at),
            expires_at=thread_expires_datetime(state.expires_at),
        )

    @staticmethod
    def _copy_thread_values(record: AgUiThreadRecord, state: ThreadState) -> None:
        """将 Thread 状态字段复制到数据库记录。

        Args:
            record: 数据库 Thread 记录。
            state: Thread 状态。

        Returns:
            无。
        """
        record.owner_user_id = state.owner_user_id
        record.agent_id = state.agent_id
        record.title = state.title
        record.created_at = datetime_from_timestamp(state.created_at)
        record.updated_at = datetime_from_timestamp(state.updated_at)
        record.expires_at = thread_expires_datetime(state.expires_at)

    async def _touch_thread(self, thread_id: str) -> None:
        """更新 Thread 最近活跃时间。

        Args:
            thread_id: Thread ID。

        Returns:
            无。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            record = await session.get(AgUiThreadRecord, thread_id)
            if record is None:
                return
            record.updated_at = utc_now()
            record.expires_at = datetime_from_timestamp(self._thread_expires_at())
            session.add(record)
            await session.commit()

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
            agent_id=record.agent_id,
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
            agent_id=state.agent_id,
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
        record.agent_id = state.agent_id
        record.status = state.status
        record.input_json = serialize_run_input(state.input)
        record.last_event_id = state.last_event_id
        record.created_at = datetime_from_timestamp(state.created_at)
        record.updated_at = datetime_from_timestamp(state.updated_at)
        record.expires_at = datetime_from_timestamp(state.expires_at)
        record.error = state.error

    async def _backfill_threads(self, user_id: str) -> None:
        """从已有 Run 回填缺失的 Thread 记录。

        Args:
            user_id: 当前用户 ID。

        Returns:
            无。
        """
        if user_id in self._backfilled_users:
            return

        await self._ensure_init()
        async with self._backfill_lock:
            if user_id in self._backfilled_users:
                return
            async with self.async_session() as session:
                run_result = await session.exec(
                    select(AgUiRunRecord)
                    .where(AgUiRunRecord.owner_user_id == user_id)
                    .order_by(AgUiRunRecord.updated_at.desc())
                )
                runs = list(run_result.all())
                if runs:
                    thread_result = await session.exec(
                        select(AgUiThreadRecord).where(
                            AgUiThreadRecord.owner_user_id == user_id
                        )
                    )
                    existing_ids = {
                        record.thread_id for record in thread_result.all()
                    }
                    for run in runs:
                        if run.thread_id in existing_ids:
                            continue
                        thread = ThreadState(
                            thread_id=run.thread_id,
                            owner_user_id=run.owner_user_id,
                            agent_id=run.agent_id,
                            title=get_thread_title(
                                deserialize_run_input(run.input_json)
                            ),
                            created_at=timestamp_from_datetime(run.created_at),
                            updated_at=timestamp_from_datetime(run.updated_at),
                            expires_at=self._thread_expires_at(
                                timestamp_from_datetime(run.updated_at)
                            ),
                        )
                        session.add(self._to_thread_record(thread))
                        existing_ids.add(run.thread_id)
                    await session.commit()
            self._backfilled_users.add(user_id)

    async def backfill_threads_from_checkpoints(
        self,
        checkpointer: Any | None,
        *,
        default_agent_id: str = "agent",
    ) -> int:
        """从 LangGraph checkpoint 回填缺失的 Thread 索引。

        Args:
            checkpointer: 已初始化的 LangGraph checkpointer。
            default_agent_id: 无法从状态判断时使用的智能体 ID。

        Returns:
            新增的 Thread 数量。
        """
        if checkpointer is None:
            return 0
        await self._ensure_init()
        async with self.async_session() as session:
            checkpoint_result = await session.exec(
                select(AgUiCheckpointRecord.thread_id)
                .where(AgUiCheckpointRecord.checkpoint_ns == "")
                .distinct()
            )
            thread_ids = list(checkpoint_result.all())
            thread_result = await session.exec(select(AgUiThreadRecord.thread_id))
            existing_ids = set(thread_result.all())

        restored = 0
        for thread_id in thread_ids:
            if thread_id in existing_ids:
                continue
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            try:
                snapshot = await checkpointer.aget_tuple(config)
            except Exception as exc:  # noqa: BLE001
                logger.warning("回填 Thread 时读取 checkpoint 失败: {}", exc)
                continue
            if snapshot is None:
                continue
            checkpoint = snapshot.checkpoint or {}
            values = checkpoint.get("channel_values", {})
            messages = values.get("messages") or []
            timestamp = checkpoint_timestamp(checkpoint.get("ts"))
            agent_id = (
                "rag"
                if values.get("index_name") or values.get("graph_name")
                else default_agent_id
            )
            state = ThreadState(
                thread_id=thread_id,
                owner_user_id=str(values.get("user_id") or "guest"),
                agent_id=agent_id,
                title=get_message_title(messages),
                created_at=timestamp,
                updated_at=timestamp,
                expires_at=self._thread_expires_at(),
            )
            if await self.create_thread(state):
                restored += 1
        if restored:
            logger.info("已从 checkpoint 回填 {} 个 Thread 索引", restored)
        return restored

    async def create_thread(self, state: ThreadState) -> bool:
        """创建 Thread。

        Args:
            state: Thread 状态。

        Returns:
            是否创建成功。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            existing = await session.get(AgUiThreadRecord, state.thread_id)
            if existing is not None:
                return False
            now = time.time()
            if state.created_at <= 0:
                state.created_at = now
            if state.updated_at <= 0:
                state.updated_at = state.created_at
            if state.expires_at <= 0:
                state.expires_at = self._thread_expires_at(state.updated_at)
            session.add(self._to_thread_record(state))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    async def get_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> ThreadState | None:
        """读取 Thread。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Thread 状态；不存在或不属于当前用户时返回 None。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiThreadRecord, thread_id)
            if record is None or (user_id is not None and record.owner_user_id != user_id):
                return None
            return self._to_thread_state(record)

    async def save_thread(self, state: ThreadState) -> None:
        """保存 Thread。

        Args:
            state: Thread 状态。

        Returns:
            无。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            record = await session.get(AgUiThreadRecord, state.thread_id)
            if record is None:
                return
            state.updated_at = time.time()
            state.expires_at = self._thread_expires_at(state.updated_at)
            self._copy_thread_values(record, state)
            session.add(record)
            await session.commit()

    async def list_threads(
        self,
        user_id: str,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[ThreadState]:
        """列出当前用户的 Thread。

        Args:
            user_id: 当前用户 ID。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Thread 列表。
        """
        await self._ensure_init()
        await self._maybe_prune()
        await self._backfill_threads(user_id)
        async with self.async_session() as session:
            statement = select(AgUiThreadRecord).where(
                AgUiThreadRecord.owner_user_id == user_id
            )
            if agent_id is not None:
                statement = statement.where(AgUiThreadRecord.agent_id == agent_id)
            result = await session.exec(
                statement.order_by(AgUiThreadRecord.updated_at.desc()).limit(limit)
            )
            return [self._to_thread_state(record) for record in result.all()]

    async def delete_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> bool:
        """删除 Thread 及其关联 Run 与事件。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            是否删除成功。
        """
        await self._ensure_init()
        await self._maybe_prune()
        async with self.async_session() as session:
            thread = await session.get(AgUiThreadRecord, thread_id)
            if thread is None or (user_id is not None and thread.owner_user_id != user_id):
                return False
            run_result = await session.exec(
                select(AgUiRunRecord.run_id).where(
                    AgUiRunRecord.thread_id == thread_id
                )
            )
            run_ids = list(run_result.all())
            if run_ids:
                await session.exec(
                    delete(AgUiRunEventRecord)
                    .where(AgUiRunEventRecord.run_id.in_(run_ids))
                    .execution_options(synchronize_session=False)
                )
                await session.exec(
                    delete(AgUiRunRecord)
                    .where(AgUiRunRecord.thread_id == thread_id)
                    .execution_options(synchronize_session=False)
                )
            await session.exec(
                delete(AgUiThreadRecord)
                .where(AgUiThreadRecord.thread_id == thread_id)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            return True

    async def list_runs_by_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[RunState]:
        """按 Thread 查询 Run。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。
            agent_id: 可选智能体 ID，用于过滤。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Run 列表。
        """
        await self._ensure_init()
        await self._maybe_prune()
        statement = select(AgUiRunRecord).where(AgUiRunRecord.thread_id == thread_id)
        if user_id is not None:
            statement = statement.where(AgUiRunRecord.owner_user_id == user_id)
        if agent_id is not None:
            statement = statement.where(AgUiRunRecord.agent_id == agent_id)
        async with self.async_session() as session:
            result = await session.exec(
                statement.order_by(AgUiRunRecord.updated_at.desc()).limit(limit)
            )
            return [self._to_state(record) for record in result.all()]

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
            await self._touch_thread(state.thread_id)

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
            await self._touch_thread(record.thread_id)
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
            await self._touch_thread(record.thread_id)
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
            select(AgUiRunEventRecord.id)
            .where(AgUiRunEventRecord.run_id == run_id)
            .order_by(AgUiRunEventRecord.event_id.desc())
        )
        event_ids = list(result.all())
        expired_event_ids = event_ids[self.max_events_per_run :]
        if expired_event_ids:
            await session.exec(
                delete(AgUiRunEventRecord)
                .where(AgUiRunEventRecord.id.in_(expired_event_ids))
                .execution_options(synchronize_session=False)
            )
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
                select(AgUiRunRecord.run_id).where(AgUiRunRecord.expires_at <= now)
            )
            expired_run_ids = list(run_result.all())
            if expired_run_ids:
                await session.exec(
                    delete(AgUiRunEventRecord)
                    .where(AgUiRunEventRecord.run_id.in_(expired_run_ids))
                    .execution_options(synchronize_session=False)
                )
            await session.exec(
                delete(AgUiRunEventRecord)
                .where(AgUiRunEventRecord.expires_at <= now)
                .execution_options(synchronize_session=False)
            )
            await session.exec(
                delete(AgUiRunRecord)
                .where(AgUiRunRecord.expires_at <= now)
                .execution_options(synchronize_session=False)
            )
            if self.thread_retention_seconds > 0:
                await session.exec(
                    delete(AgUiThreadRecord)
                    .where(AgUiThreadRecord.expires_at <= now)
                    .execution_options(synchronize_session=False)
                )
            await session.commit()
        self._last_prune_at = time.time()
        return len(expired_run_ids)

    async def close(self) -> None:
        """释放数据库连接资源。

        Args:
            无。

        Returns:
            无。
        """
        await self.engine.dispose()

    async def initialize(self) -> None:
        """初始化 SQL 存储表与索引。

        Args:
            无。

        Returns:
            无。
        """
        await self._ensure_init()


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
            thread_retention_seconds=settings.AGUI_THREAD_RETENTION_SECONDS,
            max_events_per_run=settings.AGUI_RUN_MAX_EVENTS,
            cleanup_interval_seconds=settings.AGUI_RUN_CLEANUP_INTERVAL_SECONDS,
            poll_interval_seconds=settings.AGUI_RUN_POLL_INTERVAL_SECONDS,
        )
    return InMemoryRunStore(
        retention_seconds=settings.AGUI_RUN_RETENTION_SECONDS,
        thread_retention_seconds=settings.AGUI_THREAD_RETENTION_SECONDS,
        max_events_per_run=settings.AGUI_RUN_MAX_EVENTS,
        cleanup_interval_seconds=settings.AGUI_RUN_CLEANUP_INTERVAL_SECONDS,
    )


async def restore_threads_from_checkpoints(
    run_store: RunStore,
    checkpointer: Any | None,
    *,
    default_agent_id: str = "agent",
) -> int:
    """从 checkpoint 恢复 SQL RunStore 中缺失的 Thread 索引。

    Args:
        run_store: 当前 Run/Thread 存储。
        checkpointer: LangGraph checkpointer。
        default_agent_id: 无法判断时使用的智能体 ID。

    Returns:
        恢复的 Thread 数量。
    """
    if not isinstance(run_store, SqlRunStore):
        return 0
    return await run_store.backfill_threads_from_checkpoints(
        checkpointer,
        default_agent_id=default_agent_id,
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
