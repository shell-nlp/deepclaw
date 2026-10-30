import json
import uuid
import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing

from deepclaw.web_backend.auth.service import AuthService, get_auth_service
from deepclaw.web_backend.channels.config import channel_gateway_settings
from deepclaw.web_backend.channels.models import AgentEvent
from deepclaw.web_backend.common.agui_runs import get_channel_agent_api_url


AgentSender = Callable[[dict, dict[str, str]], AsyncIterator[str]]


class AgentClient:
    """通过 AG-UI Run API 调用 Agent 的渠道客户端。"""

    def __init__(
        self,
        *,
        agent_api_url: str | None = None,
        sender: AgentSender | None = None,
        auth_service: AuthService | None = None,
    ):
        """初始化渠道 Agent 客户端。

        Args:
            agent_api_url: 可选完整覆盖 Runs URL。
            sender: 可选自定义 SSE 发送器。
            auth_service: 可选认证服务。
        """
        explicit = agent_api_url or channel_gateway_settings.CHANNEL_AGENT_API_URL or None
        self.agent_api_url = get_channel_agent_api_url(explicit_url=explicit)
        self.sender = sender or self._http_sender
        self.auth_service = auth_service or get_auth_service()

    async def stream(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        run_id: str | None = None,
        message_id: str | None = None,
        last_event_id: str | None = None,
        recover: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        """创建 AG-UI Run 并输出渠道可消费的事件。

        Args:
            query: 用户文本。
            user_id: 渠道用户 ID。
            session_id: 渠道会话对应的 thread ID。
            run_id: 持久化的 Run 标识，恢复时沿用。
            message_id: 稳定的用户消息标识。
            last_event_id: 已持久化的 SSE 游标。
            recover: 是否仅恢复已有 Run，缺失时禁止重新执行。

        Yields:
            转换后的渠道 AgentEvent。
        """
        payload = {
            "agentId": "agent",
            "threadId": session_id,
            "runId": run_id or str(uuid.uuid4()),
            "state": {"deep_thinking": True, "user_id": user_id},
            "messages": [
                {
                    "id": message_id or str(uuid.uuid4()),
                    "role": "user",
                    "content": query,
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
        issued_token = await self._issue_user_token(user_id)
        headers = self._build_headers(issued_token.token if issued_token else None)
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        if recover:
            headers["X-Deepclaw-Recover"] = "true"
        cursor = last_event_id
        finished = False
        try:
            async with aclosing(self.sender(payload, headers)) as lines:
                async for line in lines:
                    if line.strip().startswith("id:"):
                        cursor = line.strip().removeprefix("id:").strip()
                    event = self._parse_sse_line(line)
                    if event is not None:
                        event.event_id = cursor
                        finished = event.event in {"run_finished", "__interrupt__"}
                        yield event
                        if finished:
                            return
            if not finished:
                raise ConnectionError("Agent 事件流提前结束，尚未收到运行结束事件")
        finally:
            if issued_token is not None:
                await self.auth_service.revoke_token(issued_token.token)

    def _parse_sse_line(self, line: str) -> AgentEvent | None:
        """解析一行 AG-UI SSE 并转换为渠道事件。

        Args:
            line: SSE 原始行。

        Returns:
            渠道 AgentEvent；忽略无数据行和结束事件。

        Raises:
            AgentRunError: Agent 返回 RUN_ERROR 时抛出。
        """
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return None
        raw = stripped.removeprefix("data:").strip()
        if not raw or raw == "[DONE]":
            return None
        payload = json.loads(raw)
        event_type = str(payload.get("type", ""))
        if event_type in {"TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_CHUNK"}:
            delta = payload.get("delta") or payload.get("content") or ""
            return AgentEvent(event="token", data={"token": delta})
        if event_type == "TOOL_CALL_START":
            tool_call = {
                "id": payload.get("toolCallId", ""),
                "name": payload.get("toolCallName", ""),
                "args": {},
            }
            return AgentEvent(event="tool_calls", data={"tool_calls": [tool_call]})
        if event_type == "TOOL_CALL_ARGS":
            tool_call = {
                "id": payload.get("toolCallId", ""),
                "name": "",
                "args": payload.get("delta", ""),
            }
            return AgentEvent(event="tool_calls", data={"tool_calls": [tool_call]})
        if event_type == "TOOL_CALL_RESULT":
            output = {
                "tool_call_id": payload.get("toolCallId", ""),
                "content": payload.get("content", ""),
            }
            return AgentEvent(event="tool_output", data={"tool_output": [output]})
        if event_type == "CUSTOM" and payload.get("name") == "on_interrupt":
            return AgentEvent(event="__interrupt__", data={"__interrupt__": payload.get("value")})
        if event_type == "MESSAGES_SNAPSHOT":
            messages = payload.get("messages")
            if isinstance(messages, list):
                return AgentEvent(event="messages_snapshot", data={"messages": messages})
        if event_type == "RUN_FINISHED":
            outcome = payload.get("outcome")
            if isinstance(outcome, dict) and outcome.get("type") == "interrupt":
                interrupts = outcome.get("interrupts")
                if isinstance(interrupts, list) and interrupts:
                    interrupt = interrupts[0]
                    if isinstance(interrupt, dict):
                        metadata = interrupt.get("metadata")
                        langgraph = (
                            metadata.get("langgraph")
                            if isinstance(metadata, dict)
                            else None
                        )
                        raw = (
                            langgraph.get("raw")
                            if isinstance(langgraph, dict)
                            else interrupt.get("message")
                        )
                        return AgentEvent(
                            event="__interrupt__",
                            data={"__interrupt__": raw},
                        )
            return AgentEvent(event="run_finished")
        if event_type == "RUN_ERROR":
            raise AgentRunError("Agent 本次运行失败")
        return None

    async def _issue_user_token(self, user_id: str):
        """为用户签发短期内部令牌。

        Args:
            user_id: 渠道用户 ID。

        Returns:
            短期令牌对象；游客返回 None。
        """
        if not user_id or user_id == "guest":
            return None
        return await self.auth_service.issue_user_access_token(user_id=user_id)

    def _build_headers(self, token: str | None) -> dict[str, str]:
        """构造渠道调用 Runs API 的认证头。

        Args:
            token: 内部访问令牌。

        Returns:
            请求头字典。
        """
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _http_sender(
        self,
        payload: dict,
        headers: dict[str, str],
    ) -> AsyncIterator[str]:
        """通过 HTTP 创建 Run 并订阅其事件流。

        Args:
            payload: AG-UI RunAgentInput 字典。
            headers: 请求头。

        Yields:
            AG-UI SSE 原始行。
        """
        import httpx

        request_headers = {key: value for key, value in headers.items() if key != "X-Deepclaw-Recover"}
        run_id = payload["runId"]
        run_url = f"{self.agent_api_url.rstrip('/')}/{run_id}"
        timeout = httpx.Timeout(connect=channel_gateway_settings.CHANNEL_AGENT_CONNECT_TIMEOUT_SECONDS,
                                read=channel_gateway_settings.CHANNEL_AGENT_READ_TIMEOUT_SECONDS, write=30, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if headers.get("X-Deepclaw-Recover") == "true":
                response = await client.get(run_url, headers=request_headers)
                if response.status_code == 404:
                    raise RunRecoveryError("原 Run 已不存在，需要人工核对，已阻止重新执行")
            else:
                response = await client.post(
                    self.agent_api_url, json=payload,
                    headers={**request_headers, "Accept": "application/json"},
                )
            response.raise_for_status()
            cursor = headers.get("Last-Event-ID")
            events_url = f"{self.agent_api_url.rstrip('/')}/{run_id}/events"
            retries = channel_gateway_settings.CHANNEL_AGENT_STREAM_RETRIES
            for attempt in range(retries + 1):
                try:
                    event_headers = {**request_headers, "Accept": "text/event-stream"}
                    if cursor:
                        event_headers["Last-Event-ID"] = cursor
                    async with client.stream("GET", events_url, headers=event_headers) as event_response:
                        if event_response.status_code == 404:
                            raise RunRecoveryError("原 Run 已过期，已阻止重新执行")
                        event_response.raise_for_status()
                        frame_id = None
                        data_lines = []
                        async for line in event_response.aiter_lines():
                            if line.startswith("id:"):
                                frame_id = line[3:].strip()
                            elif line.startswith("data:"):
                                data_lines.append(line[5:].lstrip())
                            elif not line and data_lines:
                                data = "\n".join(data_lines)
                                event = json.loads(data)
                                if frame_id and frame_id == cursor:
                                    data_lines = []
                                    continue
                                if frame_id:
                                    yield f"id: {frame_id}"
                                yield f"data: {data}"
                                cursor = frame_id or cursor
                                frame_id, data_lines = None, []
                                if event.get("type") in {"RUN_FINISHED", "RUN_ERROR"}:
                                    return
                    raise ConnectionError("Agent SSE 在终止事件前断开")
                except (httpx.TransportError, ConnectionError):
                    if attempt == retries:
                        raise
                    await asyncio.sleep(min(2 ** attempt, 8))
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in {408, 429} and exc.response.status_code < 500:
                        raise
                    if attempt == retries:
                        raise
                    await asyncio.sleep(min(2 ** attempt, 8))


class RunRecoveryError(RuntimeError):
    """原 Run 已过期或丢失，禁止自动创建新的执行。"""


class AgentRunError(RuntimeError):
    """Agent 已报告终止错误，不能自动重新运行工具。"""
