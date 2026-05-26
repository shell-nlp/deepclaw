from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Self

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import (
    AudioContent,
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ListToolsResult,
    PaginatedRequestParams,
    ResourceLink,
    TextContent,
    TextResourceContents,
    Tool as MCPTool,
)


def _ensure_dict(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"`{name}` must be a dict")
    return value


def _load_json_config(config: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    path = Path(config)
    return _ensure_dict(json.loads(path.read_text(encoding="utf-8")), name="config")


def _infer_transport(server_config: dict[str, Any]) -> str:
    transport = server_config.get("type")
    if transport is None:
        if "command" in server_config:
            return "stdio"
        if "url" in server_config:
            return "streamable-http"
        raise ValueError("Unable to infer MCP transport from server config")

    normalized = str(transport).strip().lower()
    aliases = {
        "stdio": "stdio",
        "sse": "sse",
        "http": "streamable-http",
        "streamablehttp": "streamable-http",
        "streamable-http": "streamable-http",
        "streamable_http": "streamable-http",
    }
    if normalized not in aliases:
        raise ValueError(f"Unsupported MCP transport: {transport!r}")
    return aliases[normalized]


def _tool_name(
    tool: MCPTool,
    *,
    server_name: str | None = None,
    tool_name_prefix: bool = False,
) -> str:
    if server_name and tool_name_prefix:
        return f"{server_name}_{tool.name}"
    return tool.name


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value


def _stringify_embedded_resource(resource: Any) -> str:
    if isinstance(resource, TextResourceContents):
        return resource.text
    if isinstance(resource, BlobResourceContents):
        return (
            f"[resource blob uri={resource.uri} mime_type={resource.mimeType} "
            f"size={len(resource.blob)}]"
        )
    if isinstance(resource, ResourceLink):
        return f"[resource link name={resource.name} uri={resource.uri}]"
    return json.dumps(_dump_model(resource), ensure_ascii=False)


def _stringify_content_block(block: Any) -> str:
    if isinstance(block, TextContent):
        return block.text
    if isinstance(block, ImageContent):
        return f"[image mime_type={block.mimeType} size={len(block.data)}]"
    if isinstance(block, AudioContent):
        return f"[audio mime_type={block.mimeType} size={len(block.data)}]"
    if isinstance(block, EmbeddedResource):
        return _stringify_embedded_resource(block.resource)
    return json.dumps(_dump_model(block), ensure_ascii=False)


def _convert_tool_result(result: CallToolResult) -> tuple[str, dict[str, Any]]:
    content = "\n\n".join(
        text
        for text in (_stringify_content_block(block) for block in result.content)
        if text
    )

    artifact: dict[str, Any] = {
        "is_error": result.isError,
        "content": [_dump_model(block) for block in result.content],
    }
    if result.structuredContent is not None:
        artifact["structured_content"] = result.structuredContent
    if result.meta is not None:
        artifact["meta"] = result.meta

    if not content and result.structuredContent is not None:
        content = json.dumps(result.structuredContent, ensure_ascii=False)

    return content, artifact


def _extract_call_meta(config: RunnableConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None

    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        return None

    call_meta = metadata.get("mcp_meta")
    if call_meta is None:
        return None
    if not isinstance(call_meta, dict):
        raise TypeError("`config.metadata.mcp_meta` must be a dict")
    return call_meta


def convert_mcp_tool_to_langchain_tool(
    session: ClientSession,
    tool: MCPTool,
    *,
    server_name: str | None = None,
    tool_name_prefix: bool = False,
) -> BaseTool:
    """Convert one MCP client-side tool description into a LangChain tool."""

    async def coroutine(
        config: RunnableConfig = None,
        **arguments: Any,
    ) -> tuple[str, dict[str, Any]]:
        result = await session.call_tool(
            tool.name,
            arguments,
            meta=_extract_call_meta(config),
        )
        content, artifact = _convert_tool_result(result)
        if result.isError:
            raise ToolException(content or f"MCP tool {tool.name!r} returned an error")
        return content, artifact

    def func(
        config: RunnableConfig = None,
        **arguments: Any,
    ) -> tuple[str, dict[str, Any]]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine(config=config, **arguments))
        msg = "Synchronous invoke is not supported in a running event loop; use `ainvoke` instead."
        raise RuntimeError(msg)

    metadata: dict[str, Any] = {
        "source": "mcp_client",
        "mcp_tool_name": tool.name,
    }
    if server_name is not None:
        metadata["mcp_server_name"] = server_name
    if tool.title is not None:
        metadata["title"] = tool.title
    if tool.annotations is not None:
        metadata["annotations"] = _dump_model(tool.annotations)
    if tool.meta is not None:
        metadata["meta"] = tool.meta
    if tool.outputSchema is not None:
        metadata["output_schema"] = tool.outputSchema
    if tool.execution is not None:
        metadata["execution"] = _dump_model(tool.execution)

    return StructuredTool(
        name=_tool_name(
            tool,
            server_name=server_name,
            tool_name_prefix=tool_name_prefix,
        ),
        description=tool.description or tool.title or tool.name,
        args_schema=tool.inputSchema or {"type": "object", "properties": {}},
        func=func,
        coroutine=coroutine,
        response_format="content_and_artifact",
        metadata=metadata,
    )


def convert_mcp_tool_to_langchain_tool_from_config(
    mcp_config: str | Path | dict[str, Any],
    tool: MCPTool,
    *,
    server_name: str,
    tool_name_prefix: bool = False,
) -> BaseTool:
    """Convert an MCP tool into a LangChain tool that reconnects on each call."""

    config_source = _load_json_config(mcp_config)

    async def coroutine(
        runnable_config: RunnableConfig = None,
        **arguments: Any,
    ) -> tuple[str, dict[str, Any]]:
        async with StreamableHttpMCPClient.from_mcp_config(
            config_source,
            server_name,
            tool_name_prefix=tool_name_prefix,
        ) as client:
            result = await client._require_session().call_tool(
                tool.name,
                arguments,
                meta=_extract_call_meta(runnable_config),
            )
        content, artifact = _convert_tool_result(result)
        if result.isError:
            raise ToolException(content or f"MCP tool {tool.name!r} returned an error")
        return content, artifact

    def func(
        runnable_config: RunnableConfig = None,
        **arguments: Any,
    ) -> tuple[str, dict[str, Any]]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine(runnable_config=runnable_config, **arguments))
        msg = "Synchronous invoke is not supported in a running event loop; use `ainvoke` instead."
        raise RuntimeError(msg)

    metadata: dict[str, Any] = {
        "source": "mcp_client",
        "mcp_tool_name": tool.name,
    }
    if server_name is not None:
        metadata["mcp_server_name"] = server_name
    if tool.title is not None:
        metadata["title"] = tool.title
    if tool.annotations is not None:
        metadata["annotations"] = _dump_model(tool.annotations)
    if tool.meta is not None:
        metadata["meta"] = tool.meta
    if tool.outputSchema is not None:
        metadata["output_schema"] = tool.outputSchema
    if tool.execution is not None:
        metadata["execution"] = _dump_model(tool.execution)

    return StructuredTool(
        name=_tool_name(
            tool,
            server_name=server_name,
            tool_name_prefix=tool_name_prefix,
        ),
        description=tool.description or tool.title or tool.name,
        args_schema=tool.inputSchema or {"type": "object", "properties": {}},
        func=func,
        coroutine=coroutine,
        response_format="content_and_artifact",
        metadata=metadata,
    )


async def list_mcp_tools(session: ClientSession) -> list[MCPTool]:
    """List all tools from a client session, including paginated results."""

    tools: list[MCPTool] = []
    cursor: str | None = None

    while True:
        response: ListToolsResult = await session.list_tools(
            params=PaginatedRequestParams(cursor=cursor) if cursor is not None else None
        )
        tools.extend(response.tools)
        if not response.nextCursor:
            break
        cursor = response.nextCursor

    return tools


async def convert_client_tools_to_langchain_tools(
    session: ClientSession,
    tools: Sequence[MCPTool],
    *,
    server_name: str | None = None,
    tool_name_prefix: bool = False,
) -> list[BaseTool]:
    """Convert tools fetched by a client session into LangChain tools."""

    return [
        convert_mcp_tool_to_langchain_tool(
            session,
            tool,
            server_name=server_name,
            tool_name_prefix=tool_name_prefix,
        )
        for tool in tools
    ]


async def load_langchain_tools_from_session(
    session: ClientSession,
    *,
    server_name: str | None = None,
    tool_name_prefix: bool = False,
) -> list[BaseTool]:
    """Fetch tools from an initialized MCP client session and convert them."""

    tools = await list_mcp_tools(session)
    return await convert_client_tools_to_langchain_tools(
        session,
        tools,
        server_name=server_name,
        tool_name_prefix=tool_name_prefix,
    )


async def load_langchain_tools_from_mcp_config(
    config: str | Path | dict[str, Any],
    *,
    server_name: str,
    tool_name_prefix: bool = False,
) -> list[BaseTool]:
    """Fetch tool schemas once and build LangChain tools that reconnect on invoke."""

    async with StreamableHttpMCPClient.from_mcp_config(
        config,
        server_name,
        tool_name_prefix=tool_name_prefix,
    ) as client:
        tools = await client.list_tools()

    config_source = _load_json_config(config)
    return [
        convert_mcp_tool_to_langchain_tool_from_config(
            config_source,
            tool,
            server_name=server_name,
            tool_name_prefix=tool_name_prefix,
        )
        for tool in tools
    ]


class StreamableHttpMCPClient:
    """MCP client that supports stdio, SSE, and streamable-http server configs."""

    def __init__(
        self,
        transport: str,
        *,
        server_name: str | None = None,
        tool_name_prefix: bool = False,
        transport_options: dict[str, Any] | None = None,
        terminate_on_close: bool = True,
    ) -> None:
        known_transports = {"stdio", "sse", "streamable-http"}
        if transport in known_transports:
            self.transport = transport
            self.transport_options = transport_options or {}
        else:
            self.transport = "streamable-http"
            self.transport_options = {
                "url": transport,
                "terminate_on_close": terminate_on_close,
            }
        self.server_name = server_name
        self.tool_name_prefix = tool_name_prefix
        self.session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None

    @classmethod
    def from_server_config(
        cls,
        server_name: str,
        server_config: dict[str, Any],
        *,
        tool_name_prefix: bool = False,
    ) -> Self:
        config = _ensure_dict(server_config, name="server_config")
        transport = _infer_transport(config)

        if transport == "stdio":
            command = config.get("command")
            if not isinstance(command, str) or not command:
                raise ValueError("stdio MCP config requires a non-empty `command`")

            options: dict[str, Any] = {
                "server": StdioServerParameters(
                    command=command,
                    args=list(config.get("args") or []),
                    env=config.get("env"),
                    cwd=config.get("cwd"),
                    encoding=config.get("encoding", "utf-8"),
                    encoding_error_handler=config.get(
                        "encoding_error_handler",
                        "strict",
                    ),
                )
            }
        elif transport == "sse":
            url = config.get("url")
            if not isinstance(url, str) or not url:
                raise ValueError("SSE MCP config requires a non-empty `url`")

            options = {
                "url": url,
                "headers": config.get("headers"),
                "timeout": float(config.get("timeout", 5)),
                "sse_read_timeout": float(config.get("sse_read_timeout", 300)),
            }
        else:
            url = config.get("url")
            if not isinstance(url, str) or not url:
                raise ValueError(
                    "streamable-http MCP config requires a non-empty `url`"
                )

            headers = config.get("headers")
            timeout = config.get("timeout")
            read_timeout = config.get("sse_read_timeout")
            http_client: httpx.AsyncClient | None = None
            if headers is not None or timeout is not None or read_timeout is not None:
                timeout_obj = None
                if timeout is not None or read_timeout is not None:
                    base_timeout = float(timeout if timeout is not None else 30.0)
                    base_read_timeout = float(
                        read_timeout if read_timeout is not None else 300.0
                    )
                    timeout_obj = httpx.Timeout(
                        base_timeout,
                        read=base_read_timeout,
                    )
                http_client = httpx.AsyncClient(
                    headers=headers,
                    timeout=timeout_obj,
                    follow_redirects=True,
                )

            options = {
                "url": url,
                "http_client": http_client,
                "manage_http_client": http_client is not None,
                "terminate_on_close": bool(config.get("terminate_on_close", True)),
            }

        return cls(
            transport=transport,
            server_name=server_name,
            tool_name_prefix=tool_name_prefix,
            transport_options=options,
        )

    @classmethod
    def from_mcp_config(
        cls,
        config: str | Path | dict[str, Any],
        server_name: str,
        *,
        tool_name_prefix: bool = False,
    ) -> Self:
        root = _load_json_config(config)
        servers = _ensure_dict(root.get("mcpServers"), name="mcpServers")
        if server_name not in servers:
            raise KeyError(f"MCP server {server_name!r} not found in config")
        return cls.from_server_config(
            server_name,
            _ensure_dict(servers[server_name], name=f"mcpServers.{server_name}"),
            tool_name_prefix=tool_name_prefix,
        )

    async def __aenter__(self) -> Self:
        stack = AsyncExitStack()
        try:
            read_stream: Any
            write_stream: Any
            if self.transport == "stdio":
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(self.transport_options["server"])
                )
            elif self.transport == "sse":
                read_stream, write_stream = await stack.enter_async_context(
                    sse_client(
                        self.transport_options["url"],
                        headers=self.transport_options.get("headers"),
                        timeout=self.transport_options.get("timeout", 5),
                        sse_read_timeout=self.transport_options.get(
                            "sse_read_timeout",
                            300,
                        ),
                    )
                )
            elif self.transport == "streamable-http":
                http_client = self.transport_options.get("http_client")
                if (
                    http_client is not None
                    and self.transport_options.get("manage_http_client")
                ):
                    await stack.enter_async_context(http_client)
                read_stream, write_stream, _ = await stack.enter_async_context(
                    streamable_http_client(
                        self.transport_options["url"],
                        http_client=http_client,
                        terminate_on_close=self.transport_options.get(
                            "terminate_on_close",
                            True,
                        ),
                    )
                )
            else:
                raise ValueError(f"Unsupported MCP transport: {self.transport!r}")

            self.session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self.session.initialize()
            self._exit_stack = stack
            return self
        except Exception:
            await stack.aclose()
            raise

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc, tb)
            self._exit_stack = None
        self.session = None

    def _require_session(self) -> ClientSession:
        if self.session is None:
            raise RuntimeError("MCP client session is not initialized")
        return self.session

    async def list_tools(self) -> list[MCPTool]:
        return await list_mcp_tools(self._require_session())

    async def load_langchain_tools(self) -> list[BaseTool]:
        return await load_langchain_tools_from_session(
            self._require_session(),
            server_name=self.server_name,
            tool_name_prefix=self.tool_name_prefix,
        )


async def main() -> None:
    config = {
        "mcpServers": {
            "math": {
                "type": "streamable-http",
                "url": "http://localhost:48000/mcp",
            }
        }
    }

    async with StreamableHttpMCPClient.from_mcp_config(
        config,
        "math",
        tool_name_prefix=False,
    ) as client:
        mcp_tools = await client.list_tools()
        print(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")

        tools = await client.load_langchain_tools()
        print(f"Converted LangChain tools: {[tool.name for tool in tools]}")
        result = await tools[0].ainvoke(
            {"a": 3, "b": 5},
            config={"metadata": {"mcp_meta": {"userId": "u123456789"}}},
        )
        print(f"Call result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
