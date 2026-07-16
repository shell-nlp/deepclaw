"""通用 API 端点。

本模块通过 ``add_general_api_endpoint`` 将一个 LangGraph
``CompiledStateGraph`` 注册为 POST SSE 接口；它不是固定路由。当前应用中：

- 通用 Agent 注册为 ``/api/agent/general_api``，使用
  ``deepclaw.agents.general.context.AgentContext``；
- RAG Agent 注册为 ``/api/rag/general_api``，使用
  ``deepclaw.agents.rag.context.AgentContext``。

请求契约
--------
请求体为 ``application/json``。``query`` 与 ``resume`` 互斥；同时提供二者会抛出
异常。常规请求提供 ``query``，中断恢复请求提供 ``resume``。两者都省略时，当前实现会
以 ``None`` 作为 Agent 输入：

- ``query``：字符串，或内容块数组。文本块为
  ``{"type": "text", "text": "..."}``；图片块为
  ``{"type": "image", "url": "...", "base64": "...", "mime_type": "..."}``；
- ``resume``：传给 ``Command(resume=...)`` 的中断恢复决策；
- ``session_id``：可选，未提供时服务端生成 UUID。它会作为 LangGraph 的
  ``configurable.thread_id``，相同 ID 会续接同一检查点；
- ``stream``：默认 ``true``。无论取值如何，响应均是 SSE；``true`` 订阅
  ``messages`` 与 ``updates`` 并逐 token 输出，``false`` 仅从 ``updates``
  投影模型消息；
- Agent 上下文扩展字段：``user_id``、``internet_search``、``deep_thinking``、
  ``mcp_config``；RAG 上下文扩展字段：``user_id``、``internet_search``、
  ``deep_thinking``、``index_name``、``graph_name``。

已验证的 Python 调用示例：

.. code-block:: python

    import json
    from urllib.request import Request, urlopen

    body = json.dumps({
        "query": "南京天气怎么样",
        "session_id": "7d9a3ee6-ab86-4b5d-b31f-db62fcc2424",
        "deep_thinking": True,
    }).encode()
    request = Request(
        "http://127.0.0.1:7869/api/agent/general_api",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        for line in response:
            print(line.decode("utf-8").rstrip())

SSE 响应契约
------------
成功响应的 ``Content-Type`` 为 ``text/event-stream; charset=utf-8``。每条业务
记录占一行，格式为 ``data: <JSON>\\n\\n``，JSON 外层固定为：

.. code-block:: json

    {"event": "token|tool_calls|tool_output|__interrupt__", "data": {...}}

正常结束时，末尾发送非 JSON 的 ``data: [DONE]\\n\\n``。客户端应以 ``[DONE]``
而非连接关闭判断正常结束；未捕获异常不会转换为 SSE ``error`` 事件。

``token`` 事件的 ``data`` 始终包含：

.. code-block:: json

    {
      "token": "普通回答片段或 null",
      "id": "LangChain 消息 ID",
      "reasoning_token": "思考片段或 null",
      "tool_calls": [{"name": "...", "args": {}, "id": "..."}] 或 null,
      "usage_metadata": {"input_tokens": 0, "output_tokens": 0} 或 null
    }

完整帧样例
------------
下面每段均为客户端收到的原始 SSE ``data:`` 行；实际 ID、文本、token 用量及工具
参数会变化，但外层事件名和字段位置不变。每一行后都紧跟一个空行。

1. 模型开始/普通回答的 ``token`` 帧。模型可能先发送一个 ``token`` 为 ``null`` 的
   空内容帧，再发送实际文本；客户端应忽略 ``null`` 而不是视为结束：

   .. code-block:: text

       data: {"event":"token","data":{"token":null,"id":"lc_run--019f6a35-d8ca-7b23-b093-29e6163051b6","reasoning_token":null,"tool_calls":null,"usage_metadata":{"input_tokens":2851,"output_tokens":0,"total_tokens":2851,"input_token_details":{},"output_token_details":{}}}}

       data: {"event":"token","data":{"token":"南京今天多云，","id":"lc_run--019f6a35-d8ca-7b23-b093-29e6163051b6","reasoning_token":null,"tool_calls":null,"usage_metadata":{"input_tokens":2851,"output_tokens":1,"total_tokens":2852,"input_token_details":{},"output_token_details":{}}}}

2. 开启 ``deep_thinking`` 后的思考 ``token`` 帧。思考增量只在
   ``reasoning_token``，``token`` 通常为 ``null``；将所有非空
   ``reasoning_token`` 按到达顺序拼接即可得到完整思考文本：

   .. code-block:: text

       data: {"event":"token","data":{"token":null,"id":"lc_run--019f6a35-d8ca-7b23-b093-29e6163051b6","reasoning_token":"先判断是否需要调用天气工具。","tool_calls":null,"usage_metadata":{"input_tokens":2851,"output_tokens":2,"total_tokens":2853,"input_token_details":{},"output_token_details":{}}}}

   使用本模块顶部示例请求实际读取到 560 个 ``token`` 事件并以 ``[DONE]`` 结束；
   具体数量随模型输出变化，不能写死。

3. 含工具调用的 ``token`` 帧。此帧仍是 ``token`` 事件，``tool_calls`` 是当前模型
   消息累计到的调用列表；其中 ``name``、``args``、``id`` 是客户端执行/关联工具的
   关键字段，``type`` 由 LangChain 提供：

   .. code-block:: text

       data: {"event":"token","data":{"token":null,"id":"lc_run--019f6a36-1111-7222-b333-444444444444","reasoning_token":null,"tool_calls":[{"name":"weather","args":{"city":"南京"},"id":"call_weather_01","type":"tool_call"}],"usage_metadata":{"input_tokens":2860,"output_tokens":8,"total_tokens":2868,"input_token_details":{},"output_token_details":{}}}}

4. ``tool_calls`` 帧。它来自 LangGraph 的 ``model`` 更新，通常与上一种帧表示同一
   批调用，因此必须以 ``tool_calls[*].id`` 去重，不能因两帧而执行两次：

   .. code-block:: text

       data: {"event":"tool_calls","data":{"tool_calls":[{"name":"weather","args":{"city":"南京"},"id":"call_weather_01","type":"tool_call"}],"id":"lc_run--019f6a36-1111-7222-b333-444444444444"}}

5. ``tool_output`` 帧。``tool_output`` 直接来自 ``tools`` 节点的
   ``messages``，未在本模块中标准化。下面是单个 LangChain ``ToolMessage`` 常见的
   JSON 序列化示例；实际可以是多条消息、字符串或包含更多字段的对象，客户端应保留
   未识别字段：

   .. code-block:: text

       data: {"event":"tool_output","data":{"tool_output":[{"content":"南京：多云，20°C","additional_kwargs":{},"response_metadata":{},"type":"tool","name":"weather","id":"toolmsg-01","tool_call_id":"call_weather_01","artifact":null,"status":"success"}],"id":"lc_run--019f6a36-5555-7666-b777-888888888888"}}

   该帧外层 ``data.id`` 是服务端为工具结果生成的 ``lc_run--<UUID>``，不是
   ``tool_call_id``；关联具体调用时应读取嵌套 ToolMessage 的 ``tool_call_id``。

6. ``__interrupt__`` 帧。它表示 HITL 中间件已暂停图执行，嵌套值直接透传第一个
   LangGraph interrupt 的 ``value``。Human-in-the-Loop 中间件的标准值包含待审操作
   ``action_requests`` 及对应的 ``review_configs``，例如：

   .. code-block:: text

       data: {"event":"__interrupt__","data":{"__interrupt__":{"action_requests":[{"name":"execute_sql","arguments":{"query":"DELETE FROM records WHERE created_at < NOW() - INTERVAL '30 days'"},"description":"Tool execution pending approval\n\nTool: execute_sql\nArgs: {...}"}],"review_configs":[{"action_name":"execute_sql","allowed_decisions":["approve","reject"]}]}}}

   ``action_requests`` 中的 ``name``、``arguments`` 和 ``description`` 用于展示
   待审操作；每个 ``review_configs`` 条目的 ``allowed_decisions`` 是该操作允许的
   决策集合。不要臆测所有工具都可编辑或拒绝，必须以这份配置为准。

   恢复时保持原 ``session_id``，请求体仅传 ``resume``，其中 ``decisions`` 必须与
   ``action_requests`` 顺序一一对应。对上例的批准请求为：

   .. code-block:: json

       {
         "session_id": "7d9a3ee6-ab86-4b5d-b31f-db62fcc2424",
         "resume": {
           "decisions": [{"type": "approve"}]
         }
       }

   其他决策格式如下。``edit`` 必须提供替换后的工具名和完整参数；``reject`` 的
   ``message`` 会作为拒绝反馈交给 Agent；``respond`` 仅用于 ``ask_user`` 一类由人类
   充当工具实现的场景，它会把 ``message`` 作为成功工具结果，不能用来拒绝有副作用的
   工具：

   .. code-block:: json

       {
         "decisions": [
           {
             "type": "edit",
             "edited_action": {
               "name": "execute_sql",
               "args": {"query": "SELECT * FROM records LIMIT 10"}
             }
           },
           {"type": "reject", "message": "该操作不允许执行，请改用只读查询。"},
           {"type": "respond", "message": "用户确认的补充信息"}
         ]
       }

   单个 ``resume`` 只能选择适用于当前 ``review_configs`` 的决策类型，且不得同时
   传入 ``query``。

7. 正常结束帧不包含 JSON：

   .. code-block:: text

       data: [DONE]

事件会按 Agent 过程交错出现：思考/回答、工具调用、工具结果、再次思考/回答；不要
假设各事件类型的固定次数或固定顺序。

鉴权与用户隔离
--------------
接口通过 ``get_current_actor`` 获取身份。游客的上下文 ``user_id`` 固定为
``guest``；已登录用户的访问令牌会覆盖请求体中的 ``user_id``，调用方不能伪造其他
用户 ID。
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

            yield "data: [DONE]\n\n"
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

            yield "data: [DONE]\n\n"

        if request.stream:
            return StreamingResponse(
                stream_token_generator(),
                media_type="text/event-stream",
            )
        return StreamingResponse(generator(), media_type="text/event-stream")


