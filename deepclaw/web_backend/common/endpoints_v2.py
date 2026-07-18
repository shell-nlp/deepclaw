"""通用 API 端点（v2，基于 astream_events v3）。

与 ``endpoints.py``（v1）并行挂载，便于对照测试。正式业务路径仍走 v1；
本模块注册时路径应带 ``v2`` 前缀，例如：

- ``POST /api/agent/v2/general_api``
- ``POST /api/rag/v2/general_api``
"""

import asyncio
import inspect
import uuid
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.runnables.schema import StreamEvent
from langchain_core.utils.json import parse_partial_json
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor


def _safe_parse_args(raw: str | None) -> dict:
    """将 tool call 的 args 字符串解析为完整 dict，失败时返回 {}。"""
    try:
        return parse_partial_json(raw or "{}") or {}
    except Exception:
        logger.warning("parse_partial_json failed for args: {!r}", raw)
        return {}

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

    def format_sse(stream_response: StreamResponse) -> str:
        return f"data: {stream_response.model_dump_json()}\n\n"

    def extract_interrupt_payload(snapshot: dict | None) -> Any:
        """从 values 快照中提取 interrupt 载荷（兼容测试与旧形态）。

        Args:
            snapshot: values 投影推送的状态快照。
        """
        if not isinstance(snapshot, dict):
            return None
        interrupts = snapshot.get("__interrupt__")
        if not interrupts:
            return None
        first_interrupt = interrupts[0] if isinstance(interrupts, list) else interrupts
        return normalize_interrupt_value(first_interrupt)

    def normalize_interrupt_value(interrupt_item: Any) -> Any:
        """将 Interrupt / dict 统一成 v1 SSE 中的 value 载荷。

        Args:
            interrupt_item: v3 interrupts 列表元素或 values 中的 interrupt 项。
        """
        interrupt_value = getattr(interrupt_item, "value", interrupt_item)
        if isinstance(interrupt_value, dict) and "value" in interrupt_value:
            # 兼容 {"value": {...}} 嵌套形态
            nested = interrupt_value.get("value")
            if isinstance(nested, dict):
                return nested
        return interrupt_value

    async def collect_stream_interrupts(stream) -> list[Any]:
        """收集 v3 run stream 上的 interrupts（真实 HITL 来源）。

        Args:
            stream: astream_events(version="v3") 返回的 AsyncGraphRunStream。
        """
        interrupts_attr = getattr(stream, "interrupts", None)
        if interrupts_attr is None:
            return []
        try:
            if callable(interrupts_attr):
                result = interrupts_attr()
                interrupts = await maybe_await(result)
            else:
                interrupts = await maybe_await(interrupts_attr)
        except Exception:
            logger.exception("collect stream.interrupts failed")
            return []
        if not interrupts:
            return []
        if isinstance(interrupts, list):
            return interrupts
        return [interrupts]

    def resolve_tool_output_id(tool_call) -> str:
        """生成 tool_output 外层 id，与 v1 对齐为 lc_run--<uuid>。

        Args:
            tool_call: v3 tool_call 流对象（当前不参与 id 生成，保留参数便于后续扩展）。
        """
        return f"lc_run--{str(uuid.uuid4())}"

    async def maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def collect_projection_value(projection):
        if inspect.isawaitable(projection):
            return await projection
        if hasattr(projection, "__aiter__"):
            chunks = []
            async for chunk in projection:
                chunks.append(chunk)
            if all(isinstance(chunk, str) for chunk in chunks):
                return "".join(chunks)
            return chunks
        return projection

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
                request.query if isinstance(request.query, str) else [block.model_dump() for block in request.query]
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
            stream: AsyncIterator[StreamEvent] = await agent.astream_events(
                input_payload,
                config=config,
                version="v3",
                context=Context(**request_payload),
            )

            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def consume_messages():
                nonlocal text
                async for message in stream.messages:
                    message_id = getattr(message, "message_id", None)
                    # v3 将文本和推理拆成独立 projection，这里继续适配成旧 SSE 契约。
                    # 先顺序消费推理，再消费文本；没有推理内容时将文本做为推理输出。
                    has_reasoning = False
                    async for reasoning_delta in message.reasoning:
                        has_reasoning = True
                        text += reasoning_delta
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": None,
                            "id": message_id,
                            "reasoning_token": reasoning_delta,
                            "tool_calls": None,
                            "usage_metadata": None,
                        }
                        await queue.put(format_sse(stream_response))

                    async for token_delta in message.text:
                        text += token_delta
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": None if not has_reasoning else token_delta,
                            "id": message_id,
                            "reasoning_token": token_delta if not has_reasoning else None,
                            "tool_calls": None,
                            "usage_metadata": None,
                        }
                        await queue.put(format_sse(stream_response))

                    tool_calls_acc: dict[str, dict] = {}
                    async for tool_call_chunk in message.tool_calls:
                        chunk_id = tool_call_chunk["id"]
                        tool_calls_acc[chunk_id] = dict(tool_call_chunk)
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": None,
                            "id": message_id,
                            "reasoning_token": None,
                            "tool_calls": [
                                {
                                    **tc,
                                    "args": _safe_parse_args(tc.get("args")),
                                }
                                for tc in tool_calls_acc.values()
                            ],
                            "usage_metadata": None,
                        }
                        await queue.put(format_sse(stream_response))

                    full_message = await maybe_await(message.output)
                    message_id = getattr(full_message, "id", message_id) if not isinstance(full_message, str) else message_id
                    usage_metadata = getattr(full_message, "usage_metadata", None) if not isinstance(full_message, str) else None
                    tool_calls = getattr(full_message, "tool_calls", None) if not isinstance(full_message, str) else None

                    stream_response.event = "token"
                    stream_response.data = {
                        "token": None,
                        "id": message_id,
                        "reasoning_token": None,
                        "tool_calls": tool_calls if tool_calls else None,
                        "usage_metadata": usage_metadata,
                    }
                    await queue.put(format_sse(stream_response))

                    if tool_calls:
                        stream_response.event = "tool_calls"
                        stream_response.data = {
                            "tool_calls": tool_calls,
                            "id": message_id,
                        }
                        await queue.put(format_sse(stream_response))
                        text += f"\n{'-' * 100}\n"

            async def consume_tool_calls():
                nonlocal text
                async for tool_call in stream.tool_calls:
                    async for output_delta in tool_call.output_deltas:
                        if isinstance(output_delta, str):
                            text += output_delta
                    stream_response.event = "tool_output"
                    stream_response.data = {
                        "tool_output": [tool_call.output] if tool_call.error is None else [tool_call.error],
                        "id": resolve_tool_output_id(tool_call),
                    }
                    await queue.put(format_sse(stream_response))
                    text += f"\n工具响应： \n{tool_call.output if tool_call.error is None else tool_call.error}\n{'-' * 100}\n"

            async def consume_values():
                # 兼容测试 fixture：values 快照中直接带 __interrupt__。
                async for snapshot in stream.values:
                    interrupt_payload = extract_interrupt_payload(snapshot)
                    if interrupt_payload is None:
                        continue
                    stream_response.event = "__interrupt__"
                    stream_response.data = {"__interrupt__": interrupt_payload}
                    await queue.put(format_sse(stream_response))

            tasks = [
                asyncio.create_task(consume_messages()),
                asyncio.create_task(consume_tool_calls()),
                asyncio.create_task(consume_values()),
            ]

            async def wait_and_signal(task):
                try:
                    await task
                finally:
                    await queue.put(None)

            waiters = [asyncio.create_task(wait_and_signal(task)) for task in tasks]
            completed = 0
            try:
                while completed < len(waiters):
                    item = await queue.get()
                    if item is None:
                        completed += 1
                        continue
                    yield item
            finally:
                await asyncio.gather(*waiters)

            # queue 消费结束后再取 interrupts，并直接 yield（不能再写已结束的 queue）。
            for interrupt_item in await collect_stream_interrupts(stream):
                stream_response.event = "__interrupt__"
                stream_response.data = {
                    "__interrupt__": normalize_interrupt_value(interrupt_item),
                }
                yield format_sse(stream_response)

            yield "data: [DONE]\n\n"
            logger.info(f"session_id：{request.session_id} \nFinal Response: \n{text}")

        async def generator():
            """非流式 SSE：仍走 v3 事件，但并发消费以对齐 v1 的 tool_output。"""
            stream = await agent.astream_events(
                input_payload,
                config=config,
                version="v3",
                context=Context(**request_payload),
            )
            # v3 的 messages / tool_calls / values 需并行消费；
            # 顺序先耗尽 messages 会导致 tool_output 丢失。
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def consume_messages():
                async for message in stream.messages:
                    message_id = getattr(message, "message_id", None)
                    full_text = await collect_projection_value(message.text)
                    full_reasoning = await collect_projection_value(message.reasoning)

                    tool_calls_acc: dict[str, dict] = {}
                    async for tool_call_chunk in message.tool_calls:
                        chunk_id = tool_call_chunk["id"]
                        tool_calls_acc[chunk_id] = dict(tool_call_chunk)
                        stream_response.event = "token"
                        stream_response.data = {
                            "token": None,
                            "id": message_id,
                            "reasoning_token": None,
                            "tool_calls": [
                                {
                                    **tc,
                                    "args": _safe_parse_args(tc.get("args")),
                                }
                                for tc in tool_calls_acc.values()
                            ],
                            "usage_metadata": None,
                        }
                        await queue.put(format_sse(stream_response))

                    full_message = await maybe_await(message.output)
                    is_message_obj = not isinstance(full_message, str)
                    msg_id = getattr(full_message, "id", message_id) if is_message_obj else message_id
                    msg_tool_calls = full_message.tool_calls if is_message_obj and full_message.tool_calls else None
                    msg_usage = getattr(full_message, "usage_metadata", None) if is_message_obj else None
                    stream_response.event = "token"
                    stream_response.data = {
                        "token": full_text if full_reasoning else None,
                        "id": msg_id,
                        "reasoning_token": full_reasoning if full_reasoning else full_text,
                        "tool_calls": msg_tool_calls,
                        "usage_metadata": msg_usage,
                    }
                    await queue.put(format_sse(stream_response))

                    if msg_tool_calls:
                        stream_response.event = "tool_calls"
                        stream_response.data = {
                            "tool_calls": msg_tool_calls,
                            "id": msg_id,
                        }
                        await queue.put(format_sse(stream_response))

            async def consume_tool_calls():
                async for tool_call in stream.tool_calls:
                    # 先耗尽 output_deltas，确保 tool_call.output 已就绪。
                    async for _output_delta in tool_call.output_deltas:
                        pass
                    tool_output = (
                        await maybe_await(tool_call.output)
                        if tool_call.error is None
                        else await maybe_await(tool_call.error)
                    )
                    stream_response.event = "tool_output"
                    stream_response.data = {
                        "tool_output": [tool_output],
                        "id": resolve_tool_output_id(tool_call),
                    }
                    await queue.put(format_sse(stream_response))

            async def consume_values():
                # 兼容测试 fixture：values 快照中直接带 __interrupt__。
                async for snapshot in stream.values:
                    interrupt_payload = extract_interrupt_payload(snapshot)
                    if interrupt_payload is None:
                        continue
                    stream_response.event = "__interrupt__"
                    stream_response.data = {"__interrupt__": interrupt_payload}
                    await queue.put(format_sse(stream_response))

            tasks = [
                asyncio.create_task(consume_messages()),
                asyncio.create_task(consume_tool_calls()),
                asyncio.create_task(consume_values()),
            ]

            async def wait_and_signal(task):
                try:
                    await task
                finally:
                    await queue.put(None)

            waiters = [asyncio.create_task(wait_and_signal(task)) for task in tasks]
            completed = 0
            try:
                while completed < len(waiters):
                    item = await queue.get()
                    if item is None:
                        completed += 1
                        continue
                    yield item
            finally:
                await asyncio.gather(*waiters)

            # queue 消费结束后再取 interrupts，并直接 yield。
            for interrupt_item in await collect_stream_interrupts(stream):
                stream_response.event = "__interrupt__"
                stream_response.data = {
                    "__interrupt__": normalize_interrupt_value(interrupt_item),
                }
                yield format_sse(stream_response)

            yield "data: [DONE]\n\n"

        if request.stream:
            return StreamingResponse(
                stream_token_generator(),
                media_type="text/event-stream",
            )
        return StreamingResponse(generator(), media_type="text/event-stream")
