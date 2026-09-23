import asyncio

from deepclaw.web_backend.channels.agent_client import AgentClient


class FakeIssuedToken:
    """测试用短期令牌。"""

    def __init__(self, token: str):
        self.token = token


class FakeAuthService:
    """测试用认证服务。"""

    def __init__(self):
        self.issued_for: list[str] = []
        self.revoked: list[str] = []

    async def issue_user_access_token(self, *, user_id: str):
        """签发并记录用户令牌。

        Args:
            user_id: 用户 ID。
        """
        self.issued_for.append(user_id)
        return FakeIssuedToken(token=f"token-for-{user_id}")

    async def revoke_token(self, token: str) -> bool:
        """记录并撤销令牌。

        Args:
            token: 待撤销令牌。
        """
        self.revoked.append(token)
        return True


async def fake_sender(payload, headers):
    """模拟 AG-UI SSE 事件行。

    Args:
        payload: AG-UI RunAgentInput。
        headers: 请求头。
    """
    assert payload["state"]["deep_thinking"] is True
    assert payload["threadId"] == "session_1"
    assert headers == {"Authorization": "Bearer token-for-user_1"}
    yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "hello"}\n\n'
    yield 'data: {"type": "TOOL_CALL_START", "toolCallId": "call-1", "toolCallName": "demo"}\n\n'
    yield "event: ping\n\n"
    yield (
        'data: {"type": "RUN_FINISHED", "outcome": {"type": "interrupt", '
        '"interrupts": [{"id": "interrupt-1", "reason": "langgraph:interrupt", '
        '"metadata": {"langgraph": {"raw": {"question": "继续吗"}}}}]}}\n\n'
    )


def test_stream_parses_agui_sse_into_agent_events():
    """验证渠道客户端将 AG-UI 事件转换为现有渠道事件。"""
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


def test_stream_keeps_text_after_unknown_custom_event():
    """验证未知 CUSTOM 事件不会阻断后续文本。"""
    auth_service = FakeAuthService()

    async def sender(payload, headers):
        """模拟 CUSTOM 后继续输出文本。

        Args:
            payload: AG-UI RunAgentInput。
            headers: 请求头。
        """
        yield 'data: {"type": "CUSTOM", "name": "recommended_questions", "value": {"recommended_questions": []}}\n\n'
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "answer"}\n\n'

    client = AgentClient(sender=sender, auth_service=auth_service)

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

    assert ["token"] == [item.event for item in result]
    assert result[0].data["token"] == "answer"


def test_stream_maps_messages_snapshot_to_channel_event():
    """验证消息快照事件被转换为渠道可消费的事件。"""
    auth_service = FakeAuthService()

    async def sender(payload, headers):
        """模拟只输出消息快照的事件流。

        Args:
            payload: AG-UI RunAgentInput。
            headers: 请求头。
        """
        yield (
            'data: {"type": "MESSAGES_SNAPSHOT", "messages": ['
            '{"id": "m1", "role": "user", "content": "hello"}, '
            '{"id": "m2", "role": "assistant", "content": "快照回复"}]}\n\n'
        )

    client = AgentClient(sender=sender, auth_service=auth_service)

    async def collect():
        """收集渠道事件。

        Args:
            无。

        Returns:
            渠道事件列表。
        """
        return [
            event
            async for event in client.stream(
                query="hello",
                user_id="user_1",
                session_id="session_1",
            )
        ]

    result = asyncio.run(collect())

    assert [item.event for item in result] == ["messages_snapshot"]
    assert result[0].data["messages"][-1]["content"] == "快照回复"
