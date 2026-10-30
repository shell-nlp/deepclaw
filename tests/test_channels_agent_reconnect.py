"""验证 HTTP 创建幂等、SSE 断流重连和终止语义。"""

import asyncio
import json

import httpx
import pytest

from deepclaw.web_backend.channels.agent_client import AgentClient, RunRecoveryError


def test_sse_disconnect_reconnects_original_run_with_cursor(monkeypatch):
    """断流后携带已收到游标续接，禁止重复 POST。

    Args:
        monkeypatch: 隔离 HTTP 客户端。
    """
    requests = []
    original = httpx.AsyncClient

    def handler(request):
        """模拟一次无终止事件的 SSE EOF。

        Args:
            request: HTTP 请求。
        """
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"runId": "run"})
        if len(requests) == 2:
            return httpx.Response(200, text='id: run:1\ndata: {"type":"TEXT_MESSAGE_CONTENT","delta":"前"}\n\n')
        assert request.headers["Last-Event-ID"] == "run:1"
        return httpx.Response(200, text='id: run:2\ndata: {"type":"TEXT_MESSAGE_CONTENT","delta":"后"}\n\nid: run:3\ndata: {"type":"RUN_FINISHED"}\n\n')

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    async def run():
        client = AgentClient(agent_api_url="http://agent/api/agui/runs")
        result = [event async for event in client.stream(query="问题", user_id="guest", session_id="thread", run_id="run")]
        assert [event.event for event in result] == ["token", "token", "run_finished"]
        assert [event.event_id for event in result] == ["run:1", "run:2", "run:3"]
        assert len([request for request in requests if request.method == "POST"]) == 1
        assert json.loads(requests[0].content)["runId"] == "run"
    asyncio.run(run())


def test_recovery_missing_run_never_creates_replacement(monkeypatch):
    """Run 过期时只报告不确定状态。

    Args:
        monkeypatch: 隔离 HTTP 客户端。
    """
    requests = []
    original = httpx.AsyncClient

    def handler(request):
        """返回原 Run 不存在。

        Args:
            request: HTTP 请求。
        """
        requests.append(request)
        return httpx.Response(404)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))

    async def run():
        client = AgentClient(agent_api_url="http://agent/api/agui/runs")
        with pytest.raises(RunRecoveryError):
            _ = [event async for event in client.stream(query="问题", user_id="guest", session_id="thread", run_id="original", recover=True)]
        assert len(requests) == 1
        assert requests[0].method == "GET"
    asyncio.run(run())


def test_incomplete_custom_stream_is_not_a_success():
    """缺失终止事件的流不能默认为成功。

    Args:
        无。
    """
    async def sender(payload, headers):
        """只发送部分文本。

        Args:
            payload: Run 输入。
            headers: HTTP 请求头。
        """
        yield 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"部分结果"}'

    async def run():
        with pytest.raises(ConnectionError):
            _ = [event async for event in AgentClient(sender=sender).stream(query="问题", user_id="guest", session_id="thread")]
    asyncio.run(run())
