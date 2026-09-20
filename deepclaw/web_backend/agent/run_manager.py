from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from ag_ui.core import RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from langgraph.graph.state import CompiledStateGraph


@dataclass
class RunRecord:
    """一个 AG-UI Run 的进程内运行记录。"""

    run_id: str
    thread_id: str
    input: RunAgentInput
    status: str = "queued"
    next_event_id: int = 1
    events: list[tuple[int, str]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: str | None = None


class AgentRunManager:
    """管理 AG-UI Run 的启动、事件缓存、重放、恢复和取消。

    Args:
        graph: 已装配完成的 LangGraph Agent 图。
        config: 每次 AG-UI 运行共享的 LangGraph 配置。
    """

    def __init__(self, graph: CompiledStateGraph, config: dict[str, Any] | None = None) -> None:
        self.graph = graph
        self.config = config or {}
        self._runs: dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()

    def _snapshot(self, record: RunRecord) -> dict[str, Any]:
        """将运行记录转换为浏览器可读的 Run Snapshot。

        Args:
            record: 待读取的运行记录。

        Returns:
            Run Snapshot 字典。
        """
        return {
            "runId": record.run_id,
            "threadId": record.thread_id,
            "status": record.status,
            "lastEventId": f"{record.run_id}:{record.next_event_id - 1}",
            "eventCount": len(record.events),
            "createdAt": record.created_at,
            "updatedAt": record.updated_at,
            "error": record.error,
        }

    async def create(self, payload: RunAgentInput) -> dict[str, Any]:
        """创建并异步启动一个新的 AG-UI Run。

        Args:
            payload: AG-UI 标准 RunAgentInput。

        Returns:
            新建 Run 的 Snapshot。

        Raises:
            ValueError: run_id 或 thread_id 已有活动运行。
        """
        async with self._lock:
            existing = self._runs.get(payload.run_id)
            if existing is not None and existing.status in {"queued", "running"}:
                raise ValueError("run_id 已存在且仍在运行")
            record = RunRecord(
                run_id=payload.run_id,
                thread_id=payload.thread_id,
                input=payload,
            )
            self._runs[payload.run_id] = record
            record.task = asyncio.create_task(self._execute(record, payload))
            return self._snapshot(record)

    async def continue_run(self, run_id: str, payload: RunAgentInput) -> dict[str, Any]:
        """在同一 Run 资源下启动恢复或 Action 产生的后续执行。

        Args:
            run_id: 路径中的 Run ID。
            payload: 包含同一 thread_id 和 command.resume 的 AG-UI 输入。

        Returns:
            更新后的 Run Snapshot。

        Raises:
            ValueError: Run 不存在、仍在运行或输入 ID 不匹配。
        """
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError("Run 不存在")
            if record.status in {"queued", "running"}:
                raise ValueError("Run 仍在运行，不能重复提交恢复操作")
            if payload.run_id != run_id or payload.thread_id != record.thread_id:
                raise ValueError("run_id 或 thread_id 与当前 Run 不一致")
            record.input = payload
            record.status = "queued"
            record.error = None
            record.updated_at = time.time()
            record.task = asyncio.create_task(self._execute(record, payload))
            return self._snapshot(record)

    async def get_snapshot(self, run_id: str) -> dict[str, Any] | None:
        """读取指定 Run 的 Snapshot。

        Args:
            run_id: Run ID。

        Returns:
            Snapshot；Run 不存在时返回 None。
        """
        async with self._lock:
            record = self._runs.get(run_id)
            return self._snapshot(record) if record else None

    async def cancel(self, run_id: str) -> dict[str, Any] | None:
        """取消指定 Run 的后台任务。

        Args:
            run_id: Run ID。

        Returns:
            更新后的 Snapshot；Run 不存在时返回 None。
        """
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            record.status = "cancelled"
            record.updated_at = time.time()
            task = record.task
            if task is not None and not task.done():
                task.cancel()
            return self._snapshot(record)

    async def events(self, run_id: str, after: int = 0):
        """订阅指定 Run 的 AG-UI SSE 事件，并支持从事件序号重放。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。

        Yields:
            带有 SSE id 的 AG-UI 事件帧。

        Raises:
            ValueError: Run 不存在。
        """
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise ValueError("Run 不存在")
            replay = [frame for event_id, frame in record.events if event_id > after]
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            active = record.status in {"queued", "running"}
            if active:
                record.subscribers.add(queue)

        try:
            for frame in replay:
                yield frame
            if not active:
                return
            while True:
                frame = await queue.get()
                if frame is None:
                    return
                yield frame
        finally:
            async with self._lock:
                record = self._runs.get(run_id)
                if record is not None:
                    record.subscribers.discard(queue)

    async def _execute(self, record: RunRecord, payload: RunAgentInput) -> None:
        """执行 LangGraphAgent 并将 AG-UI 事件写入缓存和订阅者。

        Args:
            record: 当前运行记录。
            payload: 本次 AG-UI 输入。
        """
        encoder = EventEncoder()
        record.status = "running"
        record.updated_at = time.time()
        agent = LangGraphAgent(
            name="deepclaw-agent",
            graph=self.graph,
            config=dict(self.config),
            # 前端和渠道不消费原始 LangGraph 事件，关闭 RAW/raw_event 以降低流式传输体积。
            emit_raw_events=False,
        )
        try:
            async for event in agent.run(payload):
                await self._append_event(record, encoder.encode(event))
            record.status = "finished"
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.error = "运行已取消"
            await self._append_event(
                record,
                encoder.encode(
                    RunErrorEvent(
                        message=record.error,
                        code="RUN_CANCELLED",
                    )
                ),
            )
        except Exception as exc:
            record.status = "error"
            record.error = str(exc)
            await self._append_event(
                record,
                encoder.encode(RunErrorEvent(message=record.error, code="RUN_ERROR")),
            )
        finally:
            record.updated_at = time.time()
            await self._close_subscribers(record)

    async def _append_event(self, record: RunRecord, encoded: str) -> None:
        """为 AG-UI 事件追加可重放的 Run 内事件 ID。

        Args:
            record: 当前运行记录。
            encoded: EventEncoder 编码后的 AG-UI SSE 帧。
        """
        async with self._lock:
            event_id = record.next_event_id
            record.next_event_id += 1
            frame = f"id: {record.run_id}:{event_id}\n{encoded}"
            record.events.append((event_id, frame))
            record.updated_at = time.time()
            subscribers = list(record.subscribers)
        for subscriber in subscribers:
            await subscriber.put(frame)

    async def _close_subscribers(self, record: RunRecord) -> None:
        """通知所有 AG-UI 事件订阅者 Run 已结束。

        Args:
            record: 当前运行记录。
        """
        async with self._lock:
            subscribers = list(record.subscribers)
        for subscriber in subscribers:
            await subscriber.put(None)

    def snapshot_for_test(self, run_id: str) -> dict[str, Any] | None:
        """同步读取 Snapshot，供不启动事件循环的单元测试使用。

        Args:
            run_id: Run ID。

        Returns:
            Snapshot 或 None。
        """
        record = self._runs.get(run_id)
        return self._snapshot(record) if record else None
