from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from deepclaw.agents.general.agent import Agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.schemas import (
    DeleteSessionRequest,
    DeleteSessionResponse,
    GetHistoryRequest,
    SessionListResponse,
)
from deepclaw.web_backend.agent.run_store import get_run_store
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_runs import (
    cancel_agui_run,
    create_agui_run,
    delete_agui_thread,
    get_agui_run_snapshot,
    get_agui_thread_state,
    handle_agui_action,
    list_agui_thread_runs,
    list_agui_threads,
    resume_agui_run,
    stream_agui_run_events,
)
from deepclaw.web_backend.common.agui_schemas import (
    RunActionRequest,
    RunSnapshot,
    ThreadDeleteResponse,
    ThreadListResponse,
    ThreadRunListResponse,
)


_agent_graph_cache: dict[tuple[int, int, int], Any] = {}
_agent_run_manager_cache: dict[tuple[int, int, int], AgentRunManager] = {}


def get_checkpointer(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 检查点存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的检查点存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "checkpointer", None)


def get_agent_store(request: Request) -> Any | None:
    """从应用状态读取 LangGraph 长期存储。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        当前应用的长期存储，未初始化时返回 None。
    """
    return getattr(request.app.state, "store", None)


async def get_agent_graph(
    request: Request,
    checkpointer: Any | None = Depends(get_checkpointer),
    store: Any | None = Depends(get_agent_store),
) -> Any:
    """按应用状态懒加载并缓存 Agent 图。

    Args:
        request: 当前 FastAPI 请求。
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        当前应用使用的 Agent 图。
    """
    cache_key = (id(request.app), id(checkpointer), id(store))
    cached = _agent_graph_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "agent_graph_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.agent_graph_lock = lock

    async with lock:
        cached = _agent_graph_cache.get(cache_key)
        if cached is None:
            cached = Agent(
                deep_agent=True,
                checkpointer=checkpointer,
                store=store,
            ).get_agent()
            _agent_graph_cache[cache_key] = cached
    return cached


async def get_agent_run_manager(
    request: Request,
    graph: Any = Depends(get_agent_graph),
) -> AgentRunManager:
    """按 Agent 图懒加载并缓存 AG-UI Run 管理器。

    Args:
        request: 当前 FastAPI 请求。
        graph: 当前应用的 Agent 图。

    Returns:
        当前应用使用的 Run 管理器。
    """
    run_store = get_run_store()
    cache_key = (id(request.app), id(graph), id(run_store))
    cached = _agent_run_manager_cache.get(cache_key)
    if cached is not None:
        return cached

    lock = getattr(request.app.state, "agent_run_manager_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.agent_run_manager_lock = lock

    async with lock:
        cached = _agent_run_manager_cache.get(cache_key)
        if cached is None:
            cached = AgentRunManager(graph, store=run_store)
            _agent_run_manager_cache[cache_key] = cached
    return cached


def get_session_title(messages: Any) -> str | None:
    """从消息列表中提取首条用户消息作为会话标题。

    Args:
        messages: LangGraph 保存或反序列化后的消息列表。

    Returns:
        首条用户文本；没有时返回 None。
    """
    if not isinstance(messages, list):
        return None
    for message in messages:
        message_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
        if message_type != "human":
            continue
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def get_checkpoint_session_title(checkpoint: Any) -> str | None:
    """从内存检查点提取会话标题。

    Args:
        checkpoint: LangGraph 保存的检查点数据。

    Returns:
        会话标题或 None。
    """
    if not isinstance(checkpoint, dict):
        return None
    values = checkpoint.get("channel_values")
    return get_session_title(values.get("messages")) if isinstance(values, dict) else None


def get_postgres_session_title(checkpointer: Any, row: dict[str, Any]) -> str | None:
    """从 PostgreSQL 检查点 blob 反序列化会话标题。

    Args:
        checkpointer: 当前 LangGraph PostgreSQL 检查点存储。
        row: 会话列表查询返回的行。

    Returns:
        会话标题或 None。
    """
    message_type = row.get("messages_type")
    message_blob = row.get("messages_blob")
    if not isinstance(message_type, str) or message_blob is None:
        return None
    try:
        messages = checkpointer.serde.loads_typed((message_type, message_blob))
    except Exception:
        logger.exception("反序列化会话标题失败: session_id={}", row.get("thread_id"))
        return None
    return get_session_title(messages)


router = APIRouter(prefix="/api/agent")
_AGENT_ALLOWED_STATE_KEYS = {"internet_search", "deep_thinking", "mcp_config"}


@router.post(
    "/runs",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="创建 Agent AG-UI Run",
    description="创建一次 Agent 运行并返回 Run Snapshot，后续通过事件接口订阅 AG-UI 事件流。",
)
async def create_agent_run(
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """创建 Agent AG-UI Run。"""
    return await create_agui_run(manager, payload, request, actor, _AGENT_ALLOWED_STATE_KEYS)


@router.get(
    "/runs/{run_id}",
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="获取 Agent AG-UI Run",
    description="查询指定 Agent Run 的当前状态、事件游标、更新时间和错误信息。",
)
async def get_agent_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """读取 Agent AG-UI Run Snapshot。"""
    return await get_agui_run_snapshot(manager, run_id, actor)


@router.get(
    "/runs/{run_id}/events",
    tags=["agent-ag-ui"],
    summary="订阅 Agent AG-UI Run 事件",
    description="以 SSE 流式返回 Agent AG-UI 事件，支持通过 Last-Event-ID 从指定位置重放。",
)
async def agent_run_events(
    run_id: str,
    request: Request,
    after: str | None = None,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """订阅 Agent AG-UI Run 事件。"""
    return await stream_agui_run_events(manager, run_id, request, after, actor)


@router.post(
    "/runs/{run_id}/resume",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="恢复 Agent AG-UI Run",
    description="提交表单、审批或中断恢复输入，继续执行同一个 Agent Run。",
)
async def resume_agent_run(
    run_id: str,
    payload: RunAgentInput,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """恢复 Agent AG-UI Run。"""
    return await resume_agui_run(
        manager,
        run_id,
        payload,
        request,
        actor,
        _AGENT_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/actions",
    status_code=202,
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="处理 Agent AG-UI Action",
    description="将前端卡片 Action 转换为 AG-UI resume 命令并继续当前 Agent Run。",
)
async def handle_agent_action(
    run_id: str,
    payload: RunActionRequest,
    request: Request,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """处理 Agent AG-UI Action。"""
    return await handle_agui_action(
        manager,
        run_id,
        payload,
        request,
        actor,
        _AGENT_ALLOWED_STATE_KEYS,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunSnapshot,
    tags=["agent-ag-ui"],
    summary="取消 Agent AG-UI Run",
    description="请求取消指定 Agent Run，并返回取消后的 Run Snapshot。",
)
async def cancel_agent_run(
    run_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """取消 Agent AG-UI Run。"""
    return await cancel_agui_run(manager, run_id, actor)


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    tags=["agent-thread"],
    summary="查询 Thread 列表",
    description="返回当前用户可见的 Thread 列表。",
)
async def list_threads(
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """查询当前用户的 Thread 列表。"""
    return await list_agui_threads(manager, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/runs",
    response_model=ThreadRunListResponse,
    tags=["agent-thread"],
    summary="查询 Agent Thread 下的 Run",
    description="返回指定 Thread 下属于当前用户的 Run 列表。",
)
async def list_agent_thread_runs(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
):
    """查询 Agent Thread 下的 Run。"""
    return await list_agui_thread_runs(manager, thread_id, actor, limit=limit)


@router.get(
    "/threads/{thread_id}/state",
    tags=["agent-thread"],
    summary="查询 Agent Thread 状态",
    description="返回指定 Thread 的 LangGraph state。",
)
async def get_agent_thread_state(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
    graph: Any = Depends(get_agent_graph),
):
    """查询 Agent Thread 状态。"""
    return await get_agui_thread_state(manager, graph, thread_id, actor)


@router.delete(
    "/threads/{thread_id}",
    response_model=ThreadDeleteResponse,
    tags=["agent-thread"],
    summary="删除 Agent Thread",
    description="删除指定 Thread 的 checkpoint、Run 和事件记录。",
)
async def delete_agent_thread(
    thread_id: str,
    actor: CurrentActor = Depends(get_current_actor),
    manager: AgentRunManager = Depends(get_agent_run_manager),
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """删除 Agent Thread。"""
    return await delete_agui_thread(manager, checkpointer, thread_id, actor)


@router.get(
    "/get_session_list",
    response_model=SessionListResponse,
    description="获取已存在的 agent 会话 ID 列表",
    tags=["agent-state"],
    summary="查询 Agent 会话列表",
)
async def list_sessions(
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """获取检查点中已存在的会话 ID，并按最近检查点去重排序。"""
    if checkpointer is None:
        return SessionListResponse()

    if isinstance(checkpointer, AsyncPostgresSaver):
        async with checkpointer.conn.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        latest_sessions.thread_id,
                        latest_sessions.checkpoint ->> 'ts' AS updated_at,
                        messages.type AS messages_type,
                        messages.blob AS messages_blob
                    FROM (
                        SELECT DISTINCT ON (thread_id)
                            thread_id,
                            checkpoint_ns,
                            checkpoint,
                            checkpoint_id
                        FROM checkpoints
                        ORDER BY
                            thread_id,
                            (checkpoint ->> 'ts')::timestamptz DESC NULLS LAST,
                            checkpoint_id DESC
                        ) AS latest_sessions
                    LEFT JOIN checkpoint_blobs AS messages
                        ON messages.thread_id = latest_sessions.thread_id
                        AND messages.checkpoint_ns = latest_sessions.checkpoint_ns
                        AND messages.channel = 'messages'
                        AND messages.version =
                            latest_sessions.checkpoint -> 'channel_versions' ->> 'messages'
                    ORDER BY
                        (latest_sessions.checkpoint ->> 'ts')::timestamptz DESC NULLS LAST
                    """
                )
                rows = await cursor.fetchall()
        sessions = [
            {
                "session_id": row["thread_id"],
                "updated_at": row["updated_at"],
                "title": get_postgres_session_title(checkpointer, row),
            }
            for row in rows
        ]
        return SessionListResponse(sessions=sessions, total=len(sessions))

    session_checkpoints: dict[str, dict[str, Any]] = {}
    async for checkpoint in checkpointer.alist(None):
        session_id = checkpoint.config["configurable"].get("thread_id")
        if not isinstance(session_id, str) or session_id in session_checkpoints:
            continue
        checkpoint_data = getattr(checkpoint, "checkpoint", {})
        if isinstance(checkpoint_data, dict):
            session_checkpoints[session_id] = checkpoint_data
        else:
            session_checkpoints[session_id] = {}

    sessions = [
        {
            "session_id": session_id,
            "updated_at": checkpoint_data.get("ts")
            if isinstance(checkpoint_data.get("ts"), str)
            else None,
            "title": get_checkpoint_session_title(checkpoint_data),
        }
        for session_id, checkpoint_data in session_checkpoints.items()
    ]
    sessions.sort(key=lambda session: session["updated_at"] or "", reverse=True)

    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.post(
    "/delete_session",
    response_model=DeleteSessionResponse,
    description="删除指定 agent 会话的所有检查点和历史记录",
    tags=["agent-state"],
    summary="删除 Agent 会话",
)
async def delete_session(
    request: DeleteSessionRequest,
    checkpointer: Any | None = Depends(get_checkpointer),
):
    """删除指定会话的全部检查点和历史记录。

    Args:
        request: 包含待删除会话 ID 的请求体。
        checkpointer: LangGraph 检查点存储。
    """
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="检查点存储不可用")

    try:
        await checkpointer.adelete_thread(request.session_id)
    except Exception as exc:
        logger.exception("删除会话失败: session_id={}", request.session_id)
        raise HTTPException(status_code=500, detail="删除会话失败") from exc

    return DeleteSessionResponse(session_id=request.session_id)


@router.post(
    "/get_state",
    description="获取agent state",
    tags=["agent-state"],
    summary="获取 Agent 状态",
)
async def get_state(
    request: GetHistoryRequest,
    graph: Any = Depends(get_agent_graph),
):
    """获取指定会话的完整 Agent state。"""
    logger.info("入参: {}", request.model_dump_json(indent=2))
    config = {"configurable": {"thread_id": f"{request.session_id}"}}
    state_snapshot = await graph.aget_state(config)
    state = state_snapshot.values
    final_state = deepcopy(state)
    try:
        messages = final_state["messages"]
        title = messages[0].content
        final_state["title"] = title
    except (IndexError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="session_id 不存在") from exc

    return final_state

