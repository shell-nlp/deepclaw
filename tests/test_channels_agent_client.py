import asyncio

from deepclaw.web_backend.channels.agent_client import AgentClient


class FakeIssuedToken:
    def __init__(self, token: str):
        self.token = token


class FakeAuthService:
    def __init__(self):
        self.issued_for: list[str] = []
        self.revoked: list[str] = []

    async def issue_user_access_token(self, *, user_id: str):
        self.issued_for.append(user_id)
        return FakeIssuedToken(token=f"token-for-{user_id}")

    async def revoke_token(self, token: str) -> bool:
        self.revoked.append(token)
        return True


async def fake_sender(payload, headers):
    assert payload["deep_thinking"] is True
    assert headers == {"Authorization": "Bearer token-for-user_1"}
    yield 'data: {"event": "token", "data": {"token": "hello"}}\n\n'
    yield 'data: {"event": "tool_calls", "data": {"tool_calls": []}}\n\n'
    yield "event: ping\n\n"
    yield 'data: {"event": "__interrupt__", "data": {"__interrupt__": {}}}\n\n'
    yield "data: [DONE]\n\n"


def test_stream_parses_sse_data_lines_into_agent_events():
    auth_service = FakeAuthService()
    client = AgentClient(sender=fake_sender, auth_service=auth_service)

    async def collect():
        return [
            event
            async for event in client.stream(
                query="hello",
                user_id="user_1",
                session_id="session_1",
            )
        ]

    result = asyncio.run(collect())

    assert ["token", "tool_calls", "__interrupt__"] == [item.event for item in result]
    assert result[0].data["token"] == "hello"
    assert auth_service.issued_for == ["user_1"]
    assert auth_service.revoked == ["token-for-user_1"]


def test_stream_keeps_custom_sse_events_before_text_tokens():
    """渠道客户端接收 custom 事件后继续读取后续文本。"""
    auth_service = FakeAuthService()

    async def sender(payload, headers):
        """模拟 custom 事件位于文本事件之前的 SSE 响应。

        Args:
            payload: Agent 请求体。
            headers: Agent 请求头。
        """
        yield 'data: {"event": "custom", "data": {"recommended_questions": []}}\n\n'
        yield 'data: {"event": "token", "data": {"token": "answer"}}\n\n'

    client = AgentClient(sender=sender, auth_service=auth_service)

    async def collect():
        """收集渠道客户端解析出的 SSE 事件。"""
        try:
            return [
                event
                async for event in client.stream(
                    query="hello",
                    user_id="user_1",
                    session_id="session_1",
                )
            ]
        except ValueError:
            return []

    result = asyncio.run(collect())

    assert ["custom", "token"] == [item.event for item in result]
    assert result[1].data["token"] == "answer"
