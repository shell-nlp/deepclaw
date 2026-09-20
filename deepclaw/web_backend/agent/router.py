from typing import Any

from fastapi import APIRouter, Response
from fastapi.encoders import jsonable_encoder
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from pydantic import BaseModel, field_serializer

from deepclaw.agents.general.agent import Agent
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.common.agui_runs import create_agui_run_router


class GetHistoryRequest(BaseModel):
    session_id: str


class DeleteSessionRequest(BaseModel):
    session_id: str


class ApiResponse(BaseModel):
    code: str
    msg: str
    data: Any = None

    @field_serializer("data", when_used="json")
    def serialize_data(self, data: Any) -> Any:
        """将响应数据转换为 JSON 可传输的数据。

        Args:
            data: 任意响应数据。

        Returns:
            JSON 可传输的数据。
        """
        return jsonable_encoder(data)


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


def create_agent_router(checkpointer=None, store=None) -> APIRouter:
    """创建 Agent API 路由，浏览器运行入口统一使用 AG-UI。

    Args:
        checkpointer: LangGraph 检查点存储。
        store: LangGraph 长期存储。

    Returns:
        Agent API 路由器。
    """
    router = APIRouter(prefix="/api/agent")
    agent = Agent(deep_agent=True, checkpointer=checkpointer, store=store).get_agent()
    run_manager = AgentRunManager(agent)
    router.include_router(
        create_agui_run_router(
            run_manager,
            allowed_state_keys={"internet_search", "deep_thinking", "mcp_config"},
            tags=["agent-ag-ui"],
        )
    )

    @router.get(
        "/get_session_list",
        response_model=ApiResponse,
        description="获取已存在的 agent 会话 ID 列表",
        tags=["agent-state"],

        summary="查询 Agent 会话列表"
    )
    async def list_sessions():
        """获取检查点中已存在的会话 ID，并按最近检查点去重排序。"""
        if checkpointer is None:
            return ApiResponse(
                code="200",
                msg="查询成功",
                data={"sessions": [], "total": 0},
            )

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
            return ApiResponse(
                code="200",
                msg="查询成功",
                data={"sessions": sessions, "total": len(sessions)},
            )

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

        return ApiResponse(
            code="200",
            msg="查询成功",
            data={"sessions": sessions, "total": len(sessions)},
        )

    @router.post(
        "/delete_session",
        response_model=ApiResponse,
        description="删除指定 agent 会话的所有检查点和历史记录",
        tags=["agent-state"],

        summary="删除 Agent 会话"
    )
    async def delete_session(request: DeleteSessionRequest, response: Response):
        """删除指定会话的全部检查点和历史记录。

        Args:
        - request: 包含待删除会话 ID 的请求体。
        - response: HTTP 响应对象。
        """
        if checkpointer is None:
            response.status_code = 503
            return ApiResponse(code="503", msg="检查点存储不可用", data=None)

        try:
            await checkpointer.adelete_thread(request.session_id)
        except Exception:
            logger.exception("删除会话失败: session_id={}", request.session_id)
            response.status_code = 500
            return ApiResponse(code="500", msg="删除会话失败", data=None)

        return ApiResponse(
            code="200",
            msg="删除成功",
            data={"session_id": request.session_id},
        )

    @router.post(
        "/get_state",
        response_model=ApiResponse,
        description="获取agent state",
        tags=["agent-state"],

        summary="获取 Agent 状态"
    )
    async def get_state(request: GetHistoryRequest):
        """获取agent state。"""
        from copy import deepcopy

        logger.info(f"入参: {request.model_dump_json(indent=2)}")
        config = {"configurable": {"thread_id": f"{request.session_id}"}}
        state_snapshot = await agent.aget_state(config)
        state = state_snapshot.values
        final_state = deepcopy(state)
        try:
            messages = final_state["messages"]
            title = messages[0].content
            final_state["title"] = title
        except (IndexError, KeyError):
            return ApiResponse(code="400", msg="session_id 不存在", data=None)

        return ApiResponse(code="200", msg="查询成功", data=final_state)

    return router
