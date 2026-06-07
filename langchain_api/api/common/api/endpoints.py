"""通用API端点
要观察完整的响应格式请调用：
post : http://localhost:7869/api/general_api (SSE 流式响应)
请求体：
{
    "query": "南京天气怎么样",
    "deep_thinking": true
}
"""

import uuid

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from loguru import logger
from pydantic import BaseModel, ConfigDict

from langchain_api.api.common.schemas.endpoints import (
    GeneralAPIRequest,
    StreamResponse,
)
from langchain_api.auth.dependencies import CurrentActor, get_current_actor

GUEST_USER_ID = "guest"


def resolve_context_user_id(
    requested_user_id: str | None, actor: CurrentActor
) -> str:
    if actor.is_guest:
        return GUEST_USER_ID
    if actor.user_id:
        return actor.user_id
    return requested_user_id or GUEST_USER_ID


def add_general_api_endpoint(
    app: FastAPI | APIRouter,
    agent: CompiledStateGraph,
    path: str = "/api/general_api",
    context: type[BaseModel] | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
):
    """添加通用 API 端点，用于与 LangGraph 交互。

    Parameters
    ----------
    app : FastAPI
        FastAPI 应用实例
    agent : CompiledStateGraph
        编译后的 LangGraph 实例
    path : str, optional
        端点路径， by default "/api/general_api"
    context : type[BaseModel] | None, optional
        上下文对象，表示额外添加的参数， by default None

    Returns
    -------

    Raises
    ------
    ValueError
        query 和 resume 不能同时存在
    """
    # 动态创建 Request 模型
    if context is not None:
        # 如果有 context，创建包含 GeneralAPIRequest 和 context 的组合类
        class Request(GeneralAPIRequest, context):  # type: ignore
            """组合后的请求模型"""

            pass

        class Context(context):
            model_config = ConfigDict(extra="ignore")  # 忽略额外字段

    else:
        # 如果没有 context，直接使用 GeneralAPIRequest
        Request = GeneralAPIRequest

    route_name = name or f"general_api_{path.strip('/').replace('/', '_')}"

    @app.post(path, response_model=StreamResponse, name=route_name, tags=tags)
    async def general_api(
        request: Request,
        actor: CurrentActor = Depends(get_current_actor),
    ):
        request_payload = request.model_dump()
        if "user_id" in request_payload:
            request_payload["user_id"] = resolve_context_user_id(
                request_payload.get("user_id"),
                actor,
            )

        logger.debug(f"request: \n{Request(**request_payload).model_dump_json(indent=2)}")
        config = {"configurable": {"thread_id": f"{request.session_id}"}}

        update = None
        input = None

        if request.query and request.resume:
            raise ValueError("query 和 resume 不能同时存在")
        elif request.query:
            # 支持字符串或结构化多模态内容
            content = (
                request.query
                if isinstance(request.query, str)
                else [block.model_dump() for block in request.query]
            )
            update = {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            }
            input = update
        elif request.resume:
            input = Command(resume=request.resume)

        stream_response = StreamResponse()

        async def stream_token_generator():
            text = ""
            full_message = None
            async for mode, chunk in agent.astream(
                input=input,
                stream_mode=["messages", "updates"],
                config=config,
                context=Context(**request_payload),
            ):
                if mode == "messages":  # 只处理消息流
                    msg: AIMessageChunk
                    msg, metadata = chunk
                    if metadata.get("tags", []) == ["agent"]:
                        if msg:
                            full_message = (
                                msg if full_message is None else full_message + msg
                            )

                            # 直接使用msg.content作为单个token
                            stream_response.event = "token"
                            stream_response.data = {
                                "token": msg.content if msg.content else None,
                                "id": msg.id,
                                "reasoning_token": msg.additional_kwargs.get(
                                    "reasoning_content", None
                                ),
                                "tool_calls": full_message.tool_calls
                                if full_message.tool_calls
                                else None,
                                "usage_metadata": msg.usage_metadata,
                            }
                            # -------- 仅仅用于 打印 ---------
                            if msg.additional_kwargs.get("reasoning_content", None):
                                text += msg.additional_kwargs["reasoning_content"]
                            if msg.content:
                                text += msg.content
                            yield f"data: {stream_response.model_dump_json()}\n\n"
                            if msg.chunk_position == "last":
                                full_message = None
                elif mode == "updates":  # 处理更新流
                    # print(f"\n[Update]: {chunk}")

                    if "__interrupt__" in chunk:  # 处理 Human in the Loop
                        stream_response.event = "__interrupt__"
                        stream_response.data = {
                            "__interrupt__": chunk["__interrupt__"][0].value
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

                    if (
                        "model" in chunk
                        and not chunk["model"]["messages"][0].tool_calls
                    ):
                        # 这个是最后一次整体的 tool 内容
                        ...
                    if "model" in chunk and chunk["model"]["messages"][0].tool_calls:
                        stream_response.event = "tool_calls"
                        stream_response.data = {
                            "tool_calls": chunk["model"]["messages"][0].tool_calls,
                            "id": chunk["model"]["messages"][0].id,
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"
                        text += f"\n{'-' * 100}\n"

                    if "tools" in chunk:
                        stream_response.event = "tool_output"
                        stream_response.data = {
                            "tool_output": chunk["tools"]["messages"],
                            "id": f"lc_run--{str(uuid.uuid4())}",
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"
                        text += f"\n工具响应： \n{chunk['tools']['messages']}\n{'-' * 100}\n"

            logger.info(f"session_id：{request.session_id} \nFinal Response: \n{text}")

        async def generator():
            async for mode, chunk in agent.astream(
                input=input,
                stream_mode=["updates"],
                config=config,
                context=Context(**request_payload),
            ):
                if mode == "updates":
                    # print(f"\n[Update]: {chunk}")
                    if "__interrupt__" in chunk:  # 处理 Human in the Loop
                        stream_response.event = "__interrupt__"
                        stream_response.data = {
                            "__interrupt__": chunk["__interrupt__"][0].value
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

                    if (
                        "model" in chunk
                        and not chunk["model"]["messages"][0].tool_calls
                    ):
                        # 这个是最后一次整体的 tool 内容
                        ...
                    # if "model" in chunk and chunk["model"]["messages"][0].tool_calls:
                    #     stream_response.event = "tool_calls"
                    #     stream_response.data = {
                    #         "tool_calls": chunk["model"]["messages"][0].tool_calls,
                    #         "id": chunk["model"]["messages"][0].id,
                    #     }
                    #     yield f"data: {stream_response.model_dump_json()}\n\n"
                    if "model" in chunk and chunk["model"]["messages"][0]:
                        messages = chunk["model"]["messages"][0]
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": messages.content if messages.content else None,
                            "id": messages.id,
                            "reasoning_token": messages.additional_kwargs.get(
                                "reasoning_content", None
                            ),
                            "tool_calls": messages.tool_calls
                            if messages.tool_calls
                            else None,
                            "usage_metadata": messages.usage_metadata,
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

                        if messages.tool_calls:
                            stream_response.event = "tool_calls"
                            stream_response.data = {
                                "tool_calls": messages.tool_calls,
                                "id": messages.id,
                            }
                            yield f"data: {stream_response.model_dump_json()}\n\n"

                    if "tools" in chunk:
                        stream_response.event = "tool_output"
                        stream_response.data = {
                            "tool_output": chunk["tools"]["messages"],
                            "id": f"lc_run--{str(uuid.uuid4())}",
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

        if request.stream:
            return StreamingResponse(
                stream_token_generator(), media_type="text/event-stream"
            )
        else:
            return StreamingResponse(generator(), media_type="text/event-stream")
