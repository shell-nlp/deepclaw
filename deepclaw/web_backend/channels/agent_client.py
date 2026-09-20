import json
import uuid
from collections.abc import AsyncIterator, Callable

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
    ) -> AsyncIterator[AgentEvent]:
        """创建 AG-UI Run 并输出渠道可消费的事件。

        Args:
            query: 用户文本。
            user_id: 渠道用户 ID。
            session_id: 渠道会话对应的 thread ID。

        Yields:
            转换后的渠道 AgentEvent。
        """
        payload = {
            "threadId": session_id,
            "runId": str(uuid.uuid4()),
            "state": {"deep_thinking": True, "user_id": user_id},
            "messages": [
                {
                    "id": str(uuid.uuid4()),
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
        try:
            async for line in self.sender(payload, headers):
                event = self._parse_sse_line(line)
                if event is not None:
                    yield event
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
            ValueError: Agent 返回 RUN_ERROR 时抛出。
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
        if event_type == "RUN_ERROR":
            raise ValueError(str(payload.get("message") or "Agent Run failed"))
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

        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                self.agent_api_url,
                json=payload,
                headers={**headers, "Accept": "application/json"},
            )
            response.raise_for_status()
            run_id = response.json()["runId"]
            events_url = f"{self.agent_api_url.rstrip('/')}/{run_id}/events"
            async with client.stream(
                "GET",
                events_url,
                headers={**headers, "Accept": "text/event-stream"},
            ) as event_response:
                event_response.raise_for_status()
                async for line in event_response.aiter_lines():
                    yield line
