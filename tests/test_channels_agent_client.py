import unittest

from langchain_api.channels.agent_client import AgentClient


async def fake_sender(payload):
    yield 'data: {"event": "token", "data": {"token": "hello"}}\n\n'
    yield 'data: {"event": "tool_calls", "data": {"tool_calls": []}}\n\n'
    yield "event: ping\n\n"
    yield 'data: {"event": "__interrupt__", "data": {"__interrupt__": {}}}\n\n'


class AgentClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_parses_sse_data_lines_into_agent_events(self):
        client = AgentClient(sender=fake_sender)

        result = [
            event
            async for event in client.stream(
                query="hello",
                user_id="user_1",
                session_id="session_1",
            )
        ]

        self.assertEqual(["token", "tool_calls", "__interrupt__"], [item.event for item in result])
        self.assertEqual("hello", result[0].data["token"])


if __name__ == "__main__":
    unittest.main()
