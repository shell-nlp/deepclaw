import json
from collections.abc import AsyncIterator, Callable

from langchain_api.channels.models import AgentEvent
from langchain_api.settings import settings


AgentSender = Callable[[dict], AsyncIterator[str]]


class AgentClient:
    def __init__(
        self,
        *,
        agent_api_url: str | None = None,
        sender: AgentSender | None = None,
    ):
        self.agent_api_url = agent_api_url or settings.CHANNEL_AGENT_API_URL
        self.sender = sender or self._http_sender

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
        async for line in self.sender(payload):
            event = self._parse_sse_line(line)
            if event is not None:
                yield event

    def _parse_sse_line(self, line: str) -> AgentEvent | None:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return None

        raw = stripped.removeprefix("data:").strip()
        if not raw:
            return None

        return AgentEvent.model_validate(json.loads(raw))

    async def _http_sender(self, payload: dict) -> AsyncIterator[str]:
        import httpx

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.agent_api_url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    yield line
