from __future__ import annotations

import asyncio
import time
from typing import Any

from ag_ui.core import RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from deepclaw.web_backend.agent.run_store import (
    RunState,
    RunStore,
    ThreadState,
    get_or_backfill_thread,
    get_run_store,
)



class ThreadOwnershipError(ValueError):
    """Thread 归属校验失败异常。"""


def run_state_to_snapshot(state: RunState) -> dict[str, Any]:
    """将 Run 状态转换为浏览器可读 Snapshot。

    Args:
        state: 当前 Run 状态。

    Returns:
        Run Snapshot 字典。
    """
    return {
        "runId": state.run_id,
        "threadId": state.thread_id,
        "status": state.status,
        "lastEventId": f"{state.run_id}:{state.last_event_id}",
        "eventCount": state.last_event_id,
        "createdAt": state.created_at,
        "updatedAt": state.updated_at,
        "error": state.error,
    }


class AgentRunManager:
    """管理 AG-UI Run 的启动、事件缓存、重放、恢复和取消。

    Args:
        graph: 已装配完成的 LangGraph Agent 图。
        config: 每次 AG-UI 运行共享的 LangGraph 配置。
        store: 可选 Run 存储；为空时使用进程级默认存储。
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        config: dict[str, Any] | None = None,
        store: RunStore | None = None,
    ) -> None:
        """初始化 Run 管理器。

        Args:
            graph: 已装配完成的 LangGraph Agent 图。
            config: 每次 AG-UI 运行共享的 LangGraph 配置。
            store: 可选 Run 存储。
        """
        self.graph = graph
        self.config = config or {}
        self.store = store or get_run_store()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._watchers: dict[str, asyncio.Task[None]] = {}
        self._cleanup_task: asyncio.Task[None] | None = None
        self._start_cleanup_task()

    @staticmethod
    def _owner_user_id(payload: RunAgentInput) -> str:
        """从可信 AG-UI state 中提取 Run 所属用户。

        Args:
            payload: 已由路由层覆盖可信 state 的 AG-UI 输入。

        Returns:
            登录用户 ID 或 guest。
        """
        state = payload.state if isinstance(payload.state, dict) else {}
        return str(state.get("user_id") or "guest")

    @staticmethod
    def _thread_title(payload: RunAgentInput) -> str | None:
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

    async def _ensure_thread(self, payload: RunAgentInput) -> ThreadState:
        """确保当前 Run 的 Thread 存在且属于同一用户。

        Args:
            payload: 已由路由层覆盖可信 state 的 AG-UI 输入。

        Returns:
            当前 Run 对应的 Thread 状态。

        Raises:
            ThreadOwnershipError: Thread 已存在但归属其他用户。
        """
        owner_user_id = self._owner_user_id(payload)
        existing = await self.store.get_thread(payload.thread_id)
        if existing is not None:
            if existing.owner_user_id != owner_user_id:
                raise ThreadOwnershipError("thread_id 不属于当前用户")
            title = self._thread_title(payload)
            if existing.title is None and title is not None:
                existing.title = title
                await self.store.save_thread(existing)
            return existing

        state = ThreadState(
            thread_id=payload.thread_id,
            owner_user_id=owner_user_id,
            title=self._thread_title(payload),
        )
        created = await self.store.create_thread(state)
        if created:
            return state
        existing = await self.store.get_thread(payload.thread_id)
        if existing is None or existing.owner_user_id != owner_user_id:
            raise ThreadOwnershipError("thread_id 不属于当前用户")
        return existing

    def _snapshot(self, state: RunState) -> dict[str, Any]:
        """将 Run 状态转换为浏览器可读 Snapshot。

        Args:
            state: 当前 Run 状态。

        Returns:
            Run Snapshot 字典。
        """
        return run_state_to_snapshot(state)

    def _start_cleanup_task(self) -> None:
        """在当前事件循环中启动过期清理任务。

        Args:
            无。

        Returns:
            无。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._cleanup_task = loop.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """周期性清理已过期 Run。

        Args:
            无。

        Returns:
            无。
        """
        interval = float(getattr(self.store, "cleanup_interval_seconds", 60))
        while True:
            await asyncio.sleep(interval)
            try:
                await self.store.prune_expired()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("清理过期 AG-UI Run 失败")

    async def _watch_cancellation(
        self,
        run_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """监听数据库中的取消状态并取消本地执行任务。

        Args:
            run_id: Run ID。
            task: 当前 worker 中执行该 Run 的异步任务。

        Returns:
            无。
        """
        interval = float(getattr(self.store, "poll_interval_seconds", 0.5))
        try:
            while not task.done():
                state = await self.store.get_run(run_id)
                if state is None or state.status in {"cancelling", "cancelled"}:
                    task.cancel()
                    return
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

    def _start_task(self, run_id: str, payload: RunAgentInput) -> asyncio.Task[None]:
        """启动 Run 后台执行任务和取消监听任务。

        Args:
            run_id: Run ID。
            payload: AG-UI 输入。

        Returns:
            已创建的异步任务。
        """
        task = asyncio.create_task(self._execute(run_id, payload))
        self._tasks[run_id] = task
        watcher = asyncio.create_task(self._watch_cancellation(run_id, task))
        self._watchers[run_id] = watcher

        def cleanup(_: asyncio.Task[None]) -> None:
            """清理任务引用。

            Args:
                _: 已结束的执行任务。

            Returns:
                无。
            """
            self._tasks.pop(run_id, None)
            watcher.cancel()
            self._watchers.pop(run_id, None)

        task.add_done_callback(cleanup)
        return task

    async def create(self, payload: RunAgentInput) -> dict[str, Any]:
        """幂等创建并异步启动一个新的 AG-UI Run。

        Args:
            payload: AG-UI 标准 RunAgentInput。

        Returns:
            新建或已存在 Run 的 Snapshot。

        Raises:
            ValueError: run_id 已存在但归属用户或 thread_id 不一致。
        """
        await self._ensure_thread(payload)
        owner_user_id = self._owner_user_id(payload)
        existing = await self.store.get_run(payload.run_id, user_id=owner_user_id)
        if existing is not None:
            if existing.thread_id != payload.thread_id:
                raise ValueError("run_id 已存在且 thread_id 不一致")
            return self._snapshot(existing)

        state = RunState(
            run_id=payload.run_id,
            thread_id=payload.thread_id,
            input=payload,
            owner_user_id=owner_user_id,
        )
        created = await self.store.create_run(state)
        if not created:
            existing = await self.store.get_run(payload.run_id, user_id=owner_user_id)
            if existing is not None and existing.thread_id == payload.thread_id:
                return self._snapshot(existing)
            raise ValueError("run_id 已存在且不属于当前用户或 thread_id 不一致")
        self._start_task(state.run_id, payload)
        return self._snapshot(state)

    async def continue_run(
        self,
        run_id: str,
        payload: RunAgentInput,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """在同一 Run 资源下启动恢复或 Action 产生的后续执行。

        Args:
            run_id: 路径中的 Run ID。
            payload: 包含同一 thread_id 和 command.resume 的 AG-UI 输入。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            更新后的 Run Snapshot。

        Raises:
            ValueError: Run 不存在、不属于当前用户、仍在运行或输入 ID 不匹配。
        """
        state = await self.store.get_run(run_id, user_id=user_id)
        if state is None:
            raise ValueError("Run 不存在")
        if self._owner_user_id(payload) != state.owner_user_id:
            raise ValueError("Run 所属用户与当前输入不一致")
        if state.status in {"queued", "running", "cancelling"}:
            raise ValueError("Run 仍在运行，不能重复提交恢复操作")
        if payload.run_id != run_id or payload.thread_id != state.thread_id:
            raise ValueError("run_id 或 thread_id 与当前 Run 不一致")
        state.input = payload
        state.status = "queued"
        state.error = None
        state.updated_at = time.time()
        await self.store.save_run(state)
        self._start_task(run_id, payload)
        return self._snapshot(state)

    async def get_snapshot(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """读取指定 Run 的 Snapshot。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Snapshot；Run 不存在或不属于当前用户时返回 None。
        """
        state = await self.store.get_run(run_id, user_id=user_id)
        return self._snapshot(state) if state else None

    async def get_input(self, run_id: str, user_id: str | None = None) -> RunAgentInput | None:
        """读取指定 Run 最近一次输入。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            最近一次 AG-UI 输入；Run 不存在或不属于当前用户时返回 None。
        """
        state = await self.store.get_run(run_id, user_id=user_id)
        return state.input if state else None

    async def get_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> ThreadState | None:
        """读取 Thread 状态，并在必要时从历史 Run 回填。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            Thread 状态；不存在或不属于当前用户时返回 None。
        """
        return await get_or_backfill_thread(
            self.store,
            thread_id,
            user_id=user_id,
        )

    async def list_threads(
        self,
        user_id: str,
        *,
        limit: int = 100,
    ) -> list[ThreadState]:
        """列出当前用户的 Thread。

        Args:
            user_id: 当前用户 ID。
            limit: 最大返回数量。

        Returns:
            按更新时间倒序排列的 Thread 列表。
        """
        return await self.store.list_threads(user_id, limit=limit)

    async def list_thread_runs(
        self,
        thread_id: str,
        user_id: str | None = None,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]] | None:
        """查询指定 Thread 下的 Run。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。
            limit: 最大返回数量。

        Returns:
            Run Snapshot 列表；Thread 不存在或不属于当前用户时返回 None。
        """
        thread = await self.get_thread(thread_id, user_id=user_id)
        if thread is None:
            return None
        runs = await self.store.list_runs_by_thread(
            thread_id,
            user_id=user_id,
            limit=limit,
        )
        return [self._snapshot(run) for run in runs]

    async def delete_thread(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> bool:
        """删除 Thread 及其 Run 记录。

        Args:
            thread_id: Thread ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            是否删除成功。
        """
        return await self.store.delete_thread(thread_id, user_id=user_id)

    async def cancel(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """请求取消指定 Run。

        Args:
            run_id: Run ID。
            user_id: 可选当前用户 ID，用于归属校验。

        Returns:
            更新后的 Snapshot；Run 不存在或不属于当前用户时返回 None。
        """
        state = await self.store.get_run(run_id, user_id=user_id)
        if state is None:
            return None
        if state.status not in {"queued", "running", "cancelling"}:
            return self._snapshot(state)

        state = await self.store.update_run_status(run_id, "cancelling")
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        return self._snapshot(state) if state else None

    async def events(self, run_id: str, after: int = 0, user_id: str | None = None):
        """订阅指定 Run 的 AG-UI SSE 事件，并支持从事件序号重放。

        Args:
            run_id: Run ID。
            after: 只返回大于该序号的事件。
            user_id: 可选当前用户 ID，用于归属校验。

        Yields:
            带有 SSE id 的 AG-UI 事件帧。
        """
        async for event_id, encoded in self.store.subscribe(
            run_id,
            after=after,
            user_id=user_id,
        ):
            yield f"id: {run_id}:{event_id}\n{encoded}"

    async def _execute(self, run_id: str, payload: RunAgentInput) -> None:
        """执行 LangGraphAgent 并将 AG-UI 事件写入存储。

        Args:
            run_id: Run ID。
            payload: 本次 AG-UI 输入。
        """
        encoder = EventEncoder()
        await self.store.update_run_status(run_id, "running")
        agent = LangGraphAgent(
            name="deepclaw-agent",
            graph=self.graph,
            config=dict(self.config),
            # 前端和渠道不消费原始 LangGraph 事件，关闭 RAW/raw_event 以降低流式传输体积。
            emit_raw_events=False,
        )
        try:
            async for event in agent.run(payload):
                state = await self.store.get_run(run_id)
                if state is None or state.status in {"cancelling", "cancelled"}:
                    raise asyncio.CancelledError
                await self.store.append_event(run_id, encoder.encode(event))
            await self.store.update_run_status(run_id, "finished")
        except asyncio.CancelledError:
            await self.store.append_event(
                run_id,
                encoder.encode(RunErrorEvent(message="运行已取消", code="RUN_CANCELLED")),
            )
            await self.store.update_run_status(run_id, "cancelled", "运行已取消")
        except Exception as exc:
            error_message = str(exc)
            await self.store.append_event(
                run_id,
                encoder.encode(RunErrorEvent(message=error_message, code="RUN_ERROR")),
            )
            await self.store.update_run_status(run_id, "error", error_message)

    async def close(self) -> None:
        """取消活动任务并释放 Run 存储资源。

        Args:
            无。

        Returns:
            无。
        """
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
        for watcher in list(self._watchers.values()):
            watcher.cancel()
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.store.close()
