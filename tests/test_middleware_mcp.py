import asyncio
from types import SimpleNamespace

from langchain_core.messages import SystemMessage
from mcp.types import LoggingMessageNotificationParams


def test_mcp_middleware_uses_settings_config():
    """验证 MCP 中间件使用设置中的默认配置。

    Args:
        无。
    """
    from deepclaw.middleware import mcp as mcp_module

    assert mcp_module.MCPMiddleware().mcp_config is mcp_module.settings.MCP_CONFIG


def test_mcp_middleware_prepares_request_headers_without_mutating_context():
    """验证 MCP 请求头会转发且不会修改入站上下文。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCPMiddleware

    header_info = {"authorization": "Bearer request-token", "X-Request": "keep"}
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context={"header_info": header_info},
            execution_info=SimpleNamespace(thread_id="thread-1"),
        )
    )

    prepared = MCPMiddleware()._prepare_mcp_request_headers(request)

    assert prepared["Authorization"] == "Bearer request-token"
    assert "authorization" not in prepared
    assert prepared["X-Conversation-Id"] == "thread-1"
    assert prepared["X-Request"] == "keep"
    assert header_info == {"authorization": "Bearer request-token", "X-Request": "keep"}


def test_mcp_middleware_forwards_logging_notifications_to_stream_writer():
    """验证 MCP 日志通知会转换为 Agent 自定义流事件。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCPMiddleware

    streamed_events = []
    runtime = SimpleNamespace(stream_writer=streamed_events.append)
    callback = MCPMiddleware()._build_logging_callback(runtime)

    asyncio.run(
        callback(
            LoggingMessageNotificationParams(
                level="info",
                logger="demo",
                data="正在处理 step 1/5",
            )
        )
    )

    assert streamed_events == [{"mcp_info": "正在处理 step 1/5"}]


def test_mcp_middleware_injects_dynamic_tool_descriptions_once():
    """验证动态 MCP 工具描述会注入系统提示词且不会重复注入。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCP_PROMPT_MARKER, MCPMiddleware

    request = SimpleNamespace(system_message=SystemMessage(content="原始系统提示词"))
    tools = [
        SimpleNamespace(name="query_records", description="按条件查询记录。"),
        SimpleNamespace(name="undocumented", description=None),
    ]

    system_message = MCPMiddleware()._override_system_message(request, tools)

    assert system_message is not None
    system_text = "\n".join(
        str(block.get("text", ""))
        for block in system_message.content_blocks
        if isinstance(block, dict)
    )
    assert "原始系统提示词" in system_text
    assert MCP_PROMPT_MARKER in system_text
    assert "## query_records\n按条件查询记录。" in system_text
    assert "undocumented" not in system_text

    repeated = MCPMiddleware()._override_system_message(
        SimpleNamespace(system_message=system_message),
        tools,
    )
    assert repeated is system_message


def test_mcp_middleware_caches_resources_by_thread_id():
    """验证同一会话只发现一次 MCP 工具。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCPMiddleware

    middleware = MCPMiddleware()
    config_calls = []
    tool_load_calls = []
    config = {
        "mcpServers": {
            "demo": {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
            }
        }
    }
    tools = [SimpleNamespace(name="echo", description="回显输入")]

    def resolve_config(_request):
        """记录 MCP 配置解析次数。

        Args:
            _request: 当前模型调用请求。
        """
        config_calls.append(True)
        return config

    def inject_headers(mcp_config, header_info):
        """返回用于工具发现的 MCP 配置。

        Args:
            mcp_config: MCP 原始配置。
            header_info: 当前请求头。
        """
        return mcp_config

    async def load_tools(mcp_config):
        """记录 MCP 工具发现次数。

        Args:
            mcp_config: 已注入请求头的 MCP 配置。
        """
        tool_load_calls.append(mcp_config)
        return tools

    async def handler(_request):
        """模拟后续模型调用处理器。

        Args:
            _request: 覆盖后的模型调用请求。
        """
        return "handled"

    middleware._resolve_mcp_config = resolve_config
    middleware._inject_context_headers = inject_headers
    middleware.get_mcp_tools = load_tools
    request = SimpleNamespace(
        tools=[],
        system_message=None,
        runtime=SimpleNamespace(
            context=SimpleNamespace(header_info={}),
            execution_info=SimpleNamespace(thread_id="thread-cache"),
        ),
    )
    request.override = lambda **kwargs: SimpleNamespace(**(request.__dict__ | kwargs))

    asyncio.run(middleware.awrap_model_call(request, handler))
    asyncio.run(middleware.awrap_model_call(request, handler))

    assert config_calls == [True]
    assert tool_load_calls == [config]
    assert middleware._mcp_resources_by_thread_id["thread-cache"] == (config, tools)


def test_mcp_middleware_retries_after_empty_tool_discovery():
    """验证首次未发现工具时，同一会话后续请求会重新连接。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCPMiddleware

    middleware = MCPMiddleware()
    config = {
        "mcpServers": {
            "demo": {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
            }
        }
    }
    load_calls = 0

    def resolve_config(_request):
        """返回固定 MCP 配置。

        Args:
            _request: 当前模型调用请求。
        """
        return config

    def inject_headers(mcp_config, header_info):
        """返回待加载的 MCP 配置。

        Args:
            mcp_config: MCP 配置。
            header_info: 当前请求头。
        """
        return mcp_config

    async def load_tools(_mcp_config):
        """模拟连续两次均未发现工具。

        Args:
            _mcp_config: MCP 配置。
        """
        nonlocal load_calls
        load_calls += 1
        return []

    async def handler(_request):
        """模拟模型调用处理器。

        Args:
            _request: 覆盖后的模型请求。
        """
        return "handled"

    middleware._resolve_mcp_config = resolve_config
    middleware._inject_context_headers = inject_headers
    middleware.get_mcp_tools = load_tools
    request = SimpleNamespace(
        tools=[],
        system_message=None,
        runtime=SimpleNamespace(
            context=SimpleNamespace(header_info={}),
            execution_info=SimpleNamespace(thread_id="thread-retry"),
        ),
    )
    request.override = lambda **kwargs: SimpleNamespace(**(request.__dict__ | kwargs))

    asyncio.run(middleware.awrap_model_call(request, handler))
    asyncio.run(middleware.awrap_model_call(request, handler))

    assert load_calls == 2
    assert "thread-retry" not in middleware._mcp_resources_by_thread_id


def test_mcp_middleware_uses_cached_tools_for_tool_call():
    """验证工具调用复用同一会话已缓存的 MCP 工具。

    Args:
        无。
    """
    from deepclaw.middleware.mcp import MCPMiddleware

    middleware = MCPMiddleware()
    captured_config = {}

    async def invoke_tool(args, config):
        """模拟缓存 MCP 工具的调用。

        Args:
            args: 工具参数。
            config: 工具调用配置。
        """
        assert args == {"text": "hello"}
        captured_config.update(config)
        return "handled"

    async def handler(_request):
        """确保缓存命中时不会回退到默认处理器。

        Args:
            _request: 当前工具调用请求。
        """
        raise AssertionError("命中 MCP 缓存时不应调用默认处理器")

    middleware._mcp_resources_by_thread_id["thread-1"] = (
        {"mcpServers": {}},
        [SimpleNamespace(name="echo", ainvoke=invoke_tool)],
    )
    request = SimpleNamespace(
        tool_call={
            "id": "call-1",
            "name": "echo",
            "args": {"text": "hello"},
        },
        state={"user_id": "user-42"},
        runtime=SimpleNamespace(
            execution_info=SimpleNamespace(thread_id="thread-1"),
        ),
    )

    result = asyncio.run(middleware.awrap_tool_call(request, handler))

    assert result.content == "handled"
    assert result.tool_call_id == "call-1"
    assert captured_config["metadata"]["mcp_meta"] == {"userId": "user-42"}
    assert callable(captured_config["metadata"]["mcp_logging_callback"])
