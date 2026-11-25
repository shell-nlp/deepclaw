import asyncio
import socket

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP

from deepclaw.middleware.mcp import MCPMiddleware
from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor
from deepclaw.web_backend.auth.rbac import dependencies
from deepclaw.web_backend.mcp_router import McpToolsRequest, _discover_tools, _discovery_address, router


def test_list_mcp_tools_without_invoking_them(monkeypatch, free_tcp_port):
    """通过真实 MCP HTTP 会话验证无需预配置的内网清单与权限。

    Args:
        monkeypatch: 注入临时 MCP 配置与测试身份。
        free_tcp_port: 供本地 MCP 服务使用的端口。
    """
    import threading

    import uvicorn

    calls = []
    mcp = FastMCP("预览测试", stateless_http=True, json_response=True)

    @mcp.tool()
    def greet(name: str) -> str:
        """生成问候。

        Args:
            name: 收件人。
        """
        calls.append(name)
        return name

    upstream = uvicorn.Server(uvicorn.Config(
        mcp.streamable_http_app(), host="127.0.0.1", port=free_tcp_port, log_level="error",
    ))
    started = threading.Event()
    original_startup = upstream.startup

    async def startup(sockets=None):
        """在测试服务监听后通知测试线程。

        Args:
            sockets: Uvicorn 提供的监听套接字。
        """
        await original_startup(sockets)
        started.set()

    monkeypatch.setattr(upstream, "startup", startup)
    worker = threading.Thread(target=upstream.run, daemon=True)
    worker.start()
    try:
        assert started.wait(timeout=5)
        app = FastAPI()
        app.include_router(router)
        allowed = False

        def test_actor():
            """提供已登录的测试账号。

            Args:
                无。
            """
            return CurrentActor(is_guest=False, user_id="tester", email="tester@example.com", role="user")

        def check_permission(*args, **kwargs):
            """按测试步骤允许或禁止读取工具元数据。

            Args:
                args: 授权主体。
                kwargs: 资源路径与操作等授权参数。
            """
            return allowed

        app.dependency_overrides[require_authenticated_actor] = test_actor
        monkeypatch.setattr(dependencies, "is_allowed", check_permission)
        server = {"type": "streamable-http", "url": f"http://127.0.0.1:{free_tcp_port}/mcp"}
        body = {"name": "demo", "server": server}
        with TestClient(app) as client:
            assert client.post("/api/mcp/tools", json=body).status_code == 403
            allowed = True
            monkeypatch.setattr(MCPMiddleware, "mcp_config", {})
            result = client.post("/api/mcp/tools", json=body)
            assert result.status_code == 200, result.text
            assert len(result.json()) == 1
            tool = result.json()[0]
            assert tool["name"] == "greet"
            assert "生成问候" in tool["description"]
            assert tool["input_schema"]["required"] == ["name"]
            assert calls == []
    finally:
        upstream.should_exit = True
        worker.join(timeout=5)


@pytest.mark.parametrize("address", ["10.87.18.144", "192.168.143.117", "127.0.0.1", "::1"])
def test_discovery_accepts_private_addresses(monkeypatch, address):
    """验证内网、回环及 IPv6 地址无需服务端白名单。

    Args:
        monkeypatch: 替换 DNS 解析以避免依赖外部网络。
        address: 本次解析返回的目标地址。
    """
    def resolve(*args, **kwargs):
        """返回测试用的目标地址。

        Args:
            args: 待解析的地址参数。
            kwargs: 套接字类型等解析选项。
        """
        return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 8000))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    assert asyncio.run(_discovery_address(httpx.URL("http://internal.example:8000/mcp"))) == address


def test_unconfigured_stdio_still_requires_server_config(monkeypatch):
    """验证开放内网地址后 stdio 仍必须匹配服务端配置。

    Args:
        monkeypatch: 清空服务端默认 MCP 配置。
    """
    monkeypatch.setattr(MCPMiddleware, "mcp_config", {})
    with pytest.raises(HTTPException) as error:
        asyncio.run(_discover_tools(McpToolsRequest(name="local", server={"type": "stdio", "command": "test-command"})))
    assert error.value.status_code == 422
