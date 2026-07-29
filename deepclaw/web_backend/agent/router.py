from typing import Any

from ag_ui_langgraph import add_langgraph_fastapi_endpoint, LangGraphAgent
from fastapi import APIRouter, Response
from fastapi.encoders import jsonable_encoder
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from loguru import logger
from pydantic import BaseModel, field_serializer

from deepclaw.agents.general.agent import Agent
from deepclaw.agents.general.context import AgentContext
from deepclaw.web_backend.common.endpoints import (
    add_general_api_endpoint as add_general_api_endpoint_v1,
)
from deepclaw.web_backend.common.endpoints_v2 import (
    add_general_api_endpoint as add_general_api_endpoint_v2,
)


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
        """将响应数据转换为 JSON 可传输的结构。

        Args:
        - data: 任意响应数据。

        Returns:
        - JSON 可传输的数据。
        """
        return jsonable_encoder(data)


def create_agent_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/agent")
    ag_ui_router = APIRouter(tags=["agent-ag-ui"])
    general_api_router = APIRouter()
    agent = Agent(deep_agent=True, checkpointer=checkpointer, store=store).get_agent()

    add_langgraph_fastapi_endpoint(
        app=ag_ui_router,
        agent=LangGraphAgent(
            name="agent",
            description="DeepAgent service.",
            graph=agent,
        ),
        path="/ag_ui",
    )

    # v1：astream messages/updates
    add_general_api_endpoint_v1(
        app=general_api_router,
        agent=agent,
        path="/general_api",
        context=AgentContext,
        name="agent_general_api",
        tags=["agent-chat"],
    )
    # v2：astream_events v3，便于对照测试
    add_general_api_endpoint_v2(
        app=general_api_router,
        agent=agent,
        path="/v2/general_api",
        context=AgentContext,
        name="agent_general_api_v2",
        tags=["agent-chat-v2"],
    )

    router.include_router(ag_ui_router)
    router.include_router(general_api_router)

    @router.get(
        "/get_session_list",
        response_model=ApiResponse,
        description="获取已存在的 agent 会话 ID 列表",
        tags=["agent-state"],
    )
    async def list_sessions():
        """获取检查点中已存在的会话 ID，并按最近检查点去重排序。"""
        if checkpointer is None:
            return ApiResponse(
                code="200",
                msg="查询成功",
                data={"session_ids": [], "total": 0},
            )

        if isinstance(checkpointer, AsyncPostgresSaver):
            async with checkpointer.conn.connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT thread_id
                        FROM checkpoints
                        GROUP BY thread_id
                        ORDER BY MAX(checkpoint_id) DESC
                        """
                    )
                    rows = await cursor.fetchall()
            session_ids = [row["thread_id"] for row in rows]
            return ApiResponse(
                code="200",
                msg="查询成功",
                data={"session_ids": session_ids, "total": len(session_ids)},
            )

        session_ids: list[str] = []
        seen_session_ids: set[str] = set()
        async for checkpoint in checkpointer.alist(None):
            session_id = checkpoint.config["configurable"].get("thread_id")
            if not isinstance(session_id, str) or session_id in seen_session_ids:
                continue
            seen_session_ids.add(session_id)
            session_ids.append(session_id)

        return ApiResponse(
            code="200",
            msg="查询成功",
            data={"session_ids": session_ids, "total": len(session_ids)},
        )

    @router.post(
        "/delete_session",
        response_model=ApiResponse,
        description="删除指定 agent 会话的所有检查点和历史记录",
        tags=["agent-state"],
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
