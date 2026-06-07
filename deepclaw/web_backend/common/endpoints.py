"""通用 API 端点。

要观察完整的响应格式请调用：
post : http://localhost:7869/api/general_api (SSE 流式响应)
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor

GUEST_USER_ID = "guest"


class TextContentBlock(BaseModel):
    """文本内容块。"""

    type: Literal["text"] = "text"
    text: str


class ImageContentBlock(BaseModel):
    """图片内容块，支持 URL 或 base64。"""

    type: Literal["image"] = "image"
    url: str | None = None
    base64: str | None = None
    mime_type: str | None = None


ContentBlock = TextContentBlock | ImageContentBlock
MessageContent = str | list[ContentBlock]


class GeneralAPIRequest(BaseModel):
    query: MessageContent | None = Field(
        None,
        description="用户输入，支持纯文本或结构化多模态内容。",
    )
    resume: dict | None = Field(None, description="恢复信息")
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="会话 ID",
    )
    stream: bool = Field(default=True, description="是否流式响应 token")


class StreamResponse(BaseModel):
    event: Literal["token", "tool_calls", "tool_output", "__interrupt__"] = "token"
    data: dict | None = None


def resolve_context_user_id(requested_user_id: str | None, actor: CurrentActor) -> str:
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
    """添加与 LangGraph 交互的通用 SSE 端点。"""

    if context is not None:
        class Request(GeneralAPIRequest, context):  # type: ignore[misc, valid-type]
            """组合后的请求模型。"""

            pass

        class Context(context):  # type: ignore[misc, valid-type]
            model_config = ConfigDict(extra="ignore")

    else:
        Request = GeneralAPIRequest
        Context = BaseModel

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

        if request.query and request.resume:
            raise ValueError("query 和 resume 不能同时存在")

        input_payload = None
        if request.query:
            content = (
                request.query
                if isinstance(request.query, str)
                else [block.model_dump() for block in request.query]
            )
            input_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            }
        elif request.resume:
            input_payload = Command(resume=request.resume)

        stream_response = StreamResponse()

        async def stream_token_generator():
            text = ""
            full_message = None
            async for mode, chunk in agent.astream(
                input=input_payload,
                stream_mode=["messages", "updates"],
                config=config,
                context=Context(**request_payload),
            ):
                if mode == "messages":
                    msg: AIMessageChunk
                    msg, metadata = chunk
                    if metadata.get("tags", []) == ["agent"] and msg:
                        full_message = msg if full_message is None else full_message + msg
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": msg.content if msg.content else None,
                            "id": msg.id,
                            "reasoning_token": msg.additional_kwargs.get(
                                "reasoning_content",
                                None,
                            ),
                            "tool_calls": full_message.tool_calls
                            if full_message.tool_calls
                            else None,
                            "usage_metadata": msg.usage_metadata,
                        }
                        if msg.additional_kwargs.get("reasoning_content", None):
                            text += msg.additional_kwargs["reasoning_content"]
                        if msg.content:
                            text += msg.content
                        yield f"data: {stream_response.model_dump_json()}\n\n"
                        if msg.chunk_position == "last":
                            full_message = None
                elif mode == "updates":
                    if "__interrupt__" in chunk:
                        stream_response.event = "__interrupt__"
                        stream_response.data = {
                            "__interrupt__": chunk["__interrupt__"][0].value
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

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
                input=input_payload,
                stream_mode=["updates"],
                config=config,
                context=Context(**request_payload),
            ):
                if mode == "updates":
                    if "__interrupt__" in chunk:
                        stream_response.event = "__interrupt__"
                        stream_response.data = {
                            "__interrupt__": chunk["__interrupt__"][0].value
                        }
                        yield f"data: {stream_response.model_dump_json()}\n\n"

                    if "model" in chunk and chunk["model"]["messages"][0]:
                        messages = chunk["model"]["messages"][0]
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": messages.content if messages.content else None,
                            "id": messages.id,
                            "reasoning_token": messages.additional_kwargs.get(
                                "reasoning_content",
                                None,
                            ),
                            "tool_calls": messages.tool_calls if messages.tool_calls else None,
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
                stream_token_generator(),
                media_type="text/event-stream",
            )
        return StreamingResponse(generator(), media_type="text/event-stream")


