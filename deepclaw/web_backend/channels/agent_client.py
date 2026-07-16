import json
from collections.abc import AsyncIterator, Callable

from deepclaw.web_backend.auth.service import AuthService, get_auth_service
from deepclaw.web_backend.channels.config import channel_gateway_settings
from deepclaw.web_backend.channels.models import AgentEvent


AgentSender = Callable[[dict, dict[str, str]], AsyncIterator[str]]


class AgentClient:
    def __init__(
        self,
        *,
        agent_api_url: str | None = None,
        sender: AgentSender | None = None,
        auth_service: AuthService | None = None,
    ):
        self.agent_api_url = agent_api_url or channel_gateway_settings.CHANNEL_AGENT_API_URL
        self.sender = sender or self._http_sender
        self.auth_service = auth_service or get_auth_service()

    async def stream(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
    ) -> AsyncIterator[AgentEvent]:
        payload = {
            "query": query,
            "user_id": user_id,
            "session_id": session_id,
            "stream": True,
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
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return None

        raw = stripped.removeprefix("data:").strip()
        if not raw:
            return None
        if raw == "[DONE]":
            return None

        return AgentEvent.model_validate(json.loads(raw))

    async def _issue_user_token(self, user_id: str):
        if not user_id or user_id == "guest":
            return None
        return await self.auth_service.issue_user_access_token(user_id=user_id)

    def _build_headers(self, token: str | None) -> dict[str, str]:
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def _http_sender(
        self,
        payload: dict,
        headers: dict[str, str],
    ) -> AsyncIterator[str]:
        import httpx

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self.agent_api_url,
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    yield line
