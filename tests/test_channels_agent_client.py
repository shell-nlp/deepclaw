import asyncio

from deepclaw.web_backend.channels.agent_client import AgentClient


async def fake_sender(payload):
    yield 'data: {"event": "token", "data": {"token": "hello"}}\n\n'
    yield 'data: {"event": "tool_calls", "data": {"tool_calls": []}}\n\n'
    yield "event: ping\n\n"
    yield 'data: {"event": "__interrupt__", "data": {"__interrupt__": {}}}\n\n'


def test_stream_parses_sse_data_lines_into_agent_events():
    client = AgentClient(sender=fake_sender)

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

