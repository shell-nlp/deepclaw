import asyncio
import ipaddress
import socket
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, Field

from deepclaw.middleware.mcp import MCPMiddleware, MCP_SERVER_LOAD_TIMEOUT_SECONDS
from deepclaw.web_backend.auth.rbac.dependencies import require_permission
from mcp2tool.fastmcp_to_langchain import StreamableHttpMCPClient, list_mcp_tools

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
_BLOCKED_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization", "upgrade"}


class McpToolsRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    server: dict[str, Any]


class McpToolResponse(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class _DiscoveryTransport(httpx.AsyncHTTPTransport):
    def __init__(self, endpoint: httpx.URL, address: str) -> None:
        """绑定本次发现请求的原始地址与已校验的目标 IP。

        Args:
            endpoint: 已校验的远程 MCP 地址。
            address: 本次连接固定使用的 IP 地址。
        """
        super().__init__(trust_env=False)
        self.endpoint = endpoint
        self.address = address

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """仅向本次会话的原始来源发请求，保留 HTTP Host 与 TLS 校验。

        Args:
            request: MCP 客户端发出的 HTTP 请求。
        """
        url = request.url
        if (url.scheme, url.host, url.port) != (self.endpoint.scheme, self.endpoint.host, self.endpoint.port):
            raise httpx.ConnectError("MCP origin changed")
        pinned_url = url.copy_with(host=self.address)
        pinned = httpx.Request(
            request.method,
            pinned_url,
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": url.raw_host.decode("ascii")},
        )
        return await super().handle_async_request(pinned)


async def _discovery_address(endpoint: httpx.URL) -> str:
    """解析 MCP 地址，支持用户直接填写内网或公网地址。

    Args:
        endpoint: 用户配置或服务端配置中的 HTTP 地址。
    """
    port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
    entries = await asyncio.get_running_loop().getaddrinfo(endpoint.host, port, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(entry[4][0]) for entry in entries]
    if not addresses:
        raise HTTPException(422, "MCP 服务地址未解析到可用的 IP。")
    return str(addresses[0])


async def _discover_tools(payload: McpToolsRequest) -> list[McpToolResponse]:
    """用已保存的连接配置读取 MCP 工具元数据。

    Args:
        payload: 待读取的单个 MCP 服务配置。
    """
    middleware = MCPMiddleware()
    server = middleware.normalize_mcp_server_config(payload.server)
    defaults = middleware.normalize_mcp_config(middleware.mcp_config)["mcpServers"] if middleware.mcp_config else {}
    transport = str(server.get("type", "stdio" if "command" in server else "streamable-http")).strip().lower()
    if transport == "stdio":
        configured = defaults.get(payload.name)
        if not configured or configured != server:
            raise HTTPException(422, "stdio 服务需在服务端 MCP_CONFIG 配置后才能查看工具。")
        async with StreamableHttpMCPClient.from_server_config(payload.name, configured) as client:
            tools = await client.list_tools()
    elif transport in {"sse", "http", "streamablehttp", "streamable-http", "streamable_http"}:
        raw_url = server.get("url")
        if not isinstance(raw_url, str):
            raise HTTPException(422, "请检查 MCP 服务的 HTTP 地址。")
        endpoint = httpx.URL(raw_url)
        if endpoint.scheme not in {"http", "https"} or not endpoint.host or endpoint.userinfo:
            raise HTTPException(422, "请填写有效的 HTTP 或 HTTPS 服务地址。")
        address = await _discovery_address(endpoint)
        raw_headers = server.get("headers")
        headers = {
            name: value for name, value in (raw_headers.items() if isinstance(raw_headers, dict) else ())
            if name.lower() not in _BLOCKED_HEADERS and isinstance(value, str)
        }

        def make_client(**kwargs: Any) -> httpx.AsyncClient:
            """构造固定连接目标且禁止跟随重定向的 HTTP 客户端。

            Args:
                kwargs: MCP SSE 客户端传入的请求参数。
            """
            return httpx.AsyncClient(
                transport=_DiscoveryTransport(endpoint, address), trust_env=False, **kwargs
            )

        if transport == "sse":
            async with sse_client(str(endpoint), headers=headers, httpx_client_factory=make_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await list_mcp_tools(session)
        else:
            async with (
                make_client(headers=headers) as http_client,
                streamable_http_client(str(endpoint), http_client=http_client) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = await list_mcp_tools(session)
    else:
        raise HTTPException(422, "此 MCP 传输方式不支持工具预览。")

    return [
        McpToolResponse(name=tool.name, description=tool.description or "", input_schema=tool.inputSchema)
        for tool in tools
    ]


@router.post("/tools", response_model=list[McpToolResponse], dependencies=[Depends(require_permission("/agent/tools/mcp", "use"))])
async def inspect_mcp_tools(payload: McpToolsRequest) -> list[McpToolResponse]:
    """查询单个 MCP 服务公开的工具清单。

    Args:
        payload: 当前服务的保存配置。
    """
    try:
        async with asyncio.timeout(MCP_SERVER_LOAD_TIMEOUT_SECONDS):
            return await _discover_tools(payload)
    except TimeoutError as exc:
        raise HTTPException(504, "读取工具清单超时，请检查服务地址后重试。") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "无法读取工具清单，请检查服务地址、传输方式和请求头。") from exc
