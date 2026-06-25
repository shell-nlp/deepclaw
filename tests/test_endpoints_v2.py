import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.endpoints_v2 import add_general_api_endpoint


class DummyContext(BaseModel):
    user_id: str = "default"


class AsyncListIterator:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class FakeMessageStream:
    def __init__(self, *, text_chunks, reasoning_chunks, tool_call_chunks, output):
        self.text = AsyncListIterator(text_chunks)
        self.reasoning = AsyncListIterator(reasoning_chunks)
        self.tool_calls = AsyncListIterator(tool_call_chunks)
        self.output = output


class FakeToolCallStream:
    def __init__(self, *, tool_name, input_data, output_deltas, output, error=None):
        self.tool_name = tool_name
        self.input = input_data
        self.output_deltas = AsyncListIterator(output_deltas)
        self.output = output
        self.error = error


class FakeRun:
    def __init__(self):
        self.messages = AsyncListIterator(
            [
                FakeMessageStream(
                    text_chunks=["你", "好"],
                    reasoning_chunks=["先分析"],
                    tool_call_chunks=[{"name": "search", "args": '{"query":"天气"}'}],
                    output=type(
                        "OutputMessage",
                        (),
                        {
                            "id": "msg-1",
                            "tool_calls": [{"name": "search", "args": {"query": "天气"}}],
                            "usage_metadata": {"input_tokens": 3, "output_tokens": 5},
                        },
                    )(),
                )
            ]
        )
        self.tool_calls = AsyncListIterator(
            [
                FakeToolCallStream(
                    tool_name="search",
                    input_data={"query": "天气"},
                    output_deltas=["晴"],
                    output="晴天",
                )
            ]
        )
        self.values = AsyncListIterator(
            [
                {"messages": []},
                {"messages": [], "__interrupt__": [{"value": {"need": "confirm"}}]},
            ]
        )


class DummyV3Agent:
    def __init__(self):
        self.calls = []
        self.contexts = []

    async def astream_events(self, input, config=None, version="v2", **kwargs):
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "kwargs": kwargs,
            }
        )
        self.contexts.append(kwargs["context"])
        return FakeRun()


def test_general_api_v2_adapts_v3_streams_and_keeps_sse_contract():
    app = FastAPI()
    agent = DummyV3Agent()
    add_general_api_endpoint(
        app=app,
        agent=agent,
        path="/api/test/general_api_v2",
        context=DummyContext,
        name="test_general_api_v2",
        tags=["tests"],
    )
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        is_guest=False,
        user_id="user-1",
        email="user@example.com",
        role="user",
    )

    client = TestClient(app)
    response = client.post(
        "/api/test/general_api_v2",
        json={"query": "hello", "session_id": "session-v3", "stream": True},
    )

    assert response.status_code == 200
    assert len(agent.calls) == 1
    assert agent.calls[0]["version"] == "v3"
    assert agent.contexts[0].user_id == "user-1"

    payloads = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))

    token_payloads = [payload for payload in payloads if payload["event"] == "token"]
    tool_call_payloads = [payload for payload in payloads if payload["event"] == "tool_calls"]
    tool_output_payloads = [payload for payload in payloads if payload["event"] == "tool_output"]
    interrupt_payloads = [payload for payload in payloads if payload["event"] == "__interrupt__"]

    assert [payload["data"]["token"] for payload in token_payloads if payload["data"]["token"]] == ["你", "好"]
    assert [payload["data"]["reasoning_token"] for payload in token_payloads if payload["data"]["reasoning_token"]] == [
        "先分析"
    ]
    assert any(
        payload["data"]["usage_metadata"] == {"input_tokens": 3, "output_tokens": 5}
        and payload["data"]["tool_calls"] == [{"name": "search", "args": {"query": "天气"}}]
        for payload in token_payloads
    )
    assert tool_call_payloads == [
        {
            "event": "tool_calls",
            "data": {
                "tool_calls": [{"name": "search", "args": {"query": "天气"}}],
                "id": "msg-1",
            },
        }
    ]
    assert tool_output_payloads == [
        {
            "event": "tool_output",
            "data": {
                "tool_output": "晴天",
                "id": "search",
            },
        }
    ]
    assert interrupt_payloads == [
        {
            "event": "__interrupt__",
            "data": {"__interrupt__": {"need": "confirm"}},
        }
    ]


def test_general_api_v2_non_stream_uses_final_message_projection():
    app = FastAPI()
    agent = DummyV3Agent()
    add_general_api_endpoint(
        app=app,
        agent=agent,
        path="/api/test/general_api_v2",
        context=DummyContext,
        name="test_general_api_v2",
        tags=["tests"],
    )
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        is_guest=False,
        user_id="user-2",
        email="user2@example.com",
        role="user",
    )

    client = TestClient(app)
    response = client.post(
        "/api/test/general_api_v2",
        json={"query": "hello", "session_id": "session-v3-non-stream", "stream": False},
    )

    assert response.status_code == 200

    payloads = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))

    assert payloads == [
        {
            "event": "token",
            "data": {
                "token": "你好",
                "id": "msg-1",
                "reasoning_token": "先分析",
                "tool_calls": [{"name": "search", "args": {"query": "天气"}}],
                "usage_metadata": {"input_tokens": 3, "output_tokens": 5},
            },
        },
        {
            "event": "tool_calls",
            "data": {
                "tool_calls": [{"name": "search", "args": {"query": "天气"}}],
                "id": "msg-1",
            },
        },
        {
            "event": "tool_output",
            "data": {
                "tool_output": "晴天",
                "id": "search",
            },
        },
        {
            "event": "__interrupt__",
            "data": {"__interrupt__": {"need": "confirm"}},
        },
    ]
