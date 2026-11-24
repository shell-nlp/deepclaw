import asyncio
import json
from copy import deepcopy
from typing import Any, cast
from uuid import uuid4

from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ToolCallRequest,
)
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command
from loguru import logger

from deepclaw.agents.general.state import StateSchema
from deepclaw.middleware.common import get_request_header_info
from deepclaw.settings import settings
from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission
from mcp2tool.fastmcp_to_langchain import load_langchain_tools_from_mcp_config

_SKIP_FORWARD_HEADERS = frozenset({"host", "content-length"})
MCP_PROMPT_MARKER = "#以下是 MCP 动态工具"
MCP_SERVER_LOAD_TIMEOUT_SECONDS = 10


class MCPMiddleware(AgentMiddleware):
    """MCP 中间件，用于处理 MCP 相关相关的逻辑"""

    state_schema = StateSchema
    # 发布版默认配置，来自 MCP_CONFIG；与 state.mcp_config 按 server 融合。
    mcp_config: dict[str, Any] = settings.MCP_CONFIG

    def __init__(self) -> None:
        """初始化按会话隔离的 MCP 配置和工具缓存。

        Args:
            无。
        """
        super().__init__()
        self._mcp_resources_by_thread_id: dict[str, tuple[dict[str, Any], list[Any]]] = {}

    def _build_progress_callback(self, tool_call_id: str):
        """创建将 MCP 进度通知绑定到当前工具卡片的回调。

        Args:
            tool_call_id: 当前 LangChain 工具调用标识。

        Returns:
            接收 MCP 进度通知并发送 AG-UI 自定义事件的异步回调。
        """

        async def progress_callback(
            progress: float,
            total: float | None,
            message: str | None,
        ) -> None:
            """发送结构化 MCP 进度事件。

            Args:
                progress: 当前已完成进度。
                total: 可选的总进度。
                message: 可选的用户可见状态说明。
            """
            await adispatch_custom_event(
                "mcp_progress",
                {
                    "tool_call_id": tool_call_id,
                    "progress": progress,
                    "total": total,
                    "message": message,
                },
            )

        return progress_callback

    def _override_system_message(self, request: ModelRequest, tools: list[Any]) -> SystemMessage | None:
        """向系统消息注入本次动态加载 MCP 工具的名称和描述。

        Args:
            request: LangChain 当前模型调用请求。
            tools: 本次成功加载的 MCP 工具列表。

        Returns:
            包含 MCP 工具描述的系统消息；无可用描述时保留原消息。
        """
        tool_descriptions = [
            f"## {tool.name}\n{tool.description}" for tool in tools if getattr(tool, "description", None)
        ]
        if not tool_descriptions:
            return request.system_message

        prompt_suffix = f"\n\n{MCP_PROMPT_MARKER}\n" + "\n\n".join(tool_descriptions)
        if request.system_message is not None:
            if any(MCP_PROMPT_MARKER in str(block) for block in request.system_message.content_blocks):
                return request.system_message
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": prompt_suffix},
            ]
        else:
            new_system_content = [{"type": "text", "text": prompt_suffix}]

        return SystemMessage(content=cast("list[str | dict[str, str]]", new_system_content))

    def _prepare_mcp_request_headers(self, request) -> dict[str, Any]:
        """准备传给 MCP 服务的请求头。

        Args:
            request: 当前 LangChain 模型或工具调用请求。

        Returns:
            需要传给 MCP 服务的请求头。
        """
        header_info = get_request_header_info(request)
        authorization = header_info.pop("authorization", None)
        if authorization is not None:
            header_info["Authorization"] = authorization
        header_info["X-Conversation-Id"] = request.runtime.execution_info.thread_id
        header_info["X-Turn-Id"] = str(uuid4())
        return header_info

    def _resolve_mcp_config(self, request) -> dict[str, Any] | None:
        """解析本次请求实际使用的 MCP 配置，文件内配置与 state 配置融合。

        Args:
            request: 中间件包装请求对象，通过 state 携带运行参数。

        同名服务优先使用部署配置，浏览器可停用其列表中的同名服务。
        显式传入空值表示关闭总开关。
        """
        state = request.state or {}
        if "mcp_config" in state and state["mcp_config"] is None:
            return None
        context_config = state.get("mcp_config")
        defaults = self.normalize_mcp_config(self.mcp_config)["mcpServers"] if self.mcp_config else {}
        local = self.normalize_mcp_config(context_config)["mcpServers"] if context_config else {}
        servers = {}
        for name, config in (local | defaults).items():
            if config.get("disabled") is True or local.get(name, {}).get("disabled") is True:
                continue
            servers[name] = {key: value for key, value in config.items() if key != "disabled"}
        return {"mcpServers": servers} if servers else None

    def _inject_context_headers(
        self,
        mcp_config: dict[str, Any],
        header_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """将入站请求头合并进每个 MCP 服务的请求头。

        ``header_info`` 里的头会覆盖同名静态头，但逐跳头（``host``、``content-length``）
        会被自动过滤，避免污染下游请求。

        Args:
            mcp_config: 待使用的 MCP 配置。
            header_info: 入站请求的原始 HTTP 头字典。

        Returns:
            不修改原配置的、包含用户请求头的 MCP 配置。
        """
        normalized_config = deepcopy(self.normalize_mcp_config(mcp_config))
        header_info = header_info or {}

        for server_config in normalized_config["mcpServers"].values():
            headers = server_config.get("headers")
            merged_headers = dict(headers) if isinstance(headers, dict) else {}
            for name, value in header_info.items():
                if not isinstance(name, str):
                    continue
                if name.lower() in _SKIP_FORWARD_HEADERS:
                    continue
                merged_headers[name] = str(value)
            server_config["headers"] = merged_headers
        return normalized_config

    def normalize_mcp_server_config(self, server_config: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(server_config)
        transport = normalized.get("type")
        if not isinstance(transport, str):
            transport = normalized.get("transport")

        if isinstance(transport, str) and transport.strip():
            normalized["type"] = transport.strip()

        normalized.pop("transport", None)
        return normalized

    def normalize_mcp_config(self, mcp_config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(mcp_config, dict):
            raise TypeError("`mcp_config` 必须是对象")

        server_root = mcp_config.get("mcpServers")
        if not isinstance(server_root, dict):
            legacy_root = mcp_config.get("mcpServer")
            if isinstance(legacy_root, str):
                try:
                    legacy_root = json.loads(legacy_root)
                except json.JSONDecodeError as exc:
                    raise ValueError("`mcp_config.mcpServer` 必须是合法 JSON 字符串") from exc

            if not isinstance(legacy_root, dict):
                raise ValueError("`mcp_config` 必须包含 `mcpServers` 对象，或兼容的 `mcpServer` 配置")
            server_root = legacy_root

        normalized_servers = {
            name: self.normalize_mcp_server_config(server_config)
            for name, server_config in server_root.items()
            if isinstance(name, str) and isinstance(server_config, dict)
        }

        normalized_config = dict(mcp_config)
        normalized_config["mcpServers"] = normalized_servers
        normalized_config.pop("mcpServer", None)
        return normalized_config

    def get_mcp_server_names(self, mcp_config: dict[str, Any]) -> list[str]:
        normalized_config = self.normalize_mcp_config(mcp_config)
        server_root = normalized_config.get("mcpServers")
        if not isinstance(server_root, dict):
            raise ValueError("`mcp_config.mcpServers` 必须是对象")

        server_names = [
            name
            for name, server_config in server_root.items()
            if isinstance(name, str) and isinstance(server_config, dict)
        ]
        if not server_names:
            raise ValueError("`mcp_config.mcpServers` 至少需要一个有效服务配置")
        return server_names

    def get_mcp_server_config(self, mcp_config: dict[str, Any], server_name: str) -> dict[str, Any]:
        normalized_config = self.normalize_mcp_config(mcp_config)
        server_root = normalized_config.get("mcpServers")
        if not isinstance(server_root, dict):
            raise ValueError("`mcp_config.mcpServers` 必须是对象")

        server_config = server_root.get(server_name)
        if not isinstance(server_config, dict):
            raise ValueError(f"`mcpServers.{server_name}` 必须是对象")
        return server_config

    async def load_mcp_tools_for_server(
        self,
        mcp_config: dict[str, Any],
        server_name: str,
        *,
        tool_name_prefix: bool,
    ):
        server_config = self.get_mcp_server_config(mcp_config, server_name)
        try:
            tools = await asyncio.wait_for(
                load_langchain_tools_from_mcp_config(
                    mcp_config,
                    server_name=server_name,
                    tool_name_prefix=tool_name_prefix,
                ),
                timeout=MCP_SERVER_LOAD_TIMEOUT_SECONDS,
            )
            logger.info(
                "MCP 服务加载成功: server_name={}, transport={}, url={}, tool_count={}",
                server_name,
                server_config.get("type"),
                server_config.get("url"),
                len(tools),
            )
            return tools
        except asyncio.TimeoutError:
            logger.warning(
                "MCP 服务连接超时，已跳过: server_name={}, transport={}, url={}",
                server_name,
                server_config.get("type"),
                server_config.get("url"),
            )
            return []
        except asyncio.CancelledError:
            logger.warning(
                "MCP 服务连接被取消，已跳过: server_name={}, transport={}, url={}",
                server_name,
                server_config.get("type"),
                server_config.get("url"),
            )
            return []
        except Exception as exc:
            logger.warning(
                "MCP 服务加载失败，已跳过: server_name={}, transport={}, url={}, error={}",
                server_name,
                server_config.get("type"),
                server_config.get("url"),
                repr(exc),
            )
            return []

    async def get_mcp_tools(self, mcp_config):
        normalized_config = self.normalize_mcp_config(mcp_config)

        server_names = self.get_mcp_server_names(normalized_config)
        tools = []
        for server_name in server_names:
            tools.extend(
                await self.load_mcp_tools_for_server(
                    normalized_config,
                    server_name,
                    tool_name_prefix=False,
                )
            )

        tool_names = [tool.name for tool in tools]
        if len(tool_names) == len(set(tool_names)):
            return tools

        logger.warning(
            "检测到多个 MCP 服务存在同名工具，改用 `server_tool` 前缀重新加载: {}",
            tool_names,
        )
        prefixed_tools = []
        for server_name in server_names:
            prefixed_tools.extend(
                await self.load_mcp_tools_for_server(
                    normalized_config,
                    server_name,
                    tool_name_prefix=True,
                )
            )
        return prefixed_tools

    async def _can_use_mcp(self, request: ModelRequest | ToolCallRequest) -> bool:
        """校验当前运行的账号能否使用 MCP。

        Args:
            request: 智能体模型调用或工具调用请求。
        """
        server_info = getattr(request.runtime, "server_info", None)
        user_id = getattr(getattr(server_info, "user", None), "identity", None)
        return user_id is None or await agent_has_permission(user_id, "/agent/tools/mcp", "use")

    async def awrap_model_call(self, request: ModelRequest, handler):
        thread_id = request.runtime.execution_info.thread_id
        mcp_config = self._resolve_mcp_config(request)
        cached_resources = self._mcp_resources_by_thread_id.get(thread_id)
        if cached_resources is not None and cached_resources[0] != mcp_config:
            self._mcp_resources_by_thread_id.pop(thread_id, None)
            cached_resources = None
        if (cached_resources or mcp_config) and not await self._can_use_mcp(request):
            return await handler(request)
        if cached_resources is not None:
            _, tools = cached_resources
            if tools:
                logger.info("MCP 会话缓存命中: thread_id={}, tool_count={}", thread_id, len(tools))
                request = request.override(
                    tools=request.tools + tools,
                    system_message=self._override_system_message(request, tools),
                )
                return ExtendedModelResponse(
                    model_response=await handler(request),
                    command=Command(update={"mcp_tool_names": [tool.name for tool in tools]}),
                )
            self._mcp_resources_by_thread_id.pop(thread_id, None)

        if mcp_config:
            header_info = self._prepare_mcp_request_headers(request)
            connection_config = self._inject_context_headers(
                mcp_config,
                header_info=header_info,
            )
            current_tools = request.tools
            tools = await self.get_mcp_tools(connection_config)
            if tools:
                self._mcp_resources_by_thread_id[thread_id] = (mcp_config, tools)
            mcp_tool_names = [tool.name for tool in tools]
            if mcp_tool_names:
                logger.info(f"加载新的MCP工具名称: {mcp_tool_names}")
                pass
            else:
                logger.warning("MCP 已启用，但当前没有成功加载任何工具，将回退为无 MCP 工具继续对话")
            request = request.override(
                tools=current_tools + tools,
                system_message=self._override_system_message(request, tools),
            )
            update = {"mcp_tool_names": mcp_tool_names}
            return ExtendedModelResponse(
                model_response=await handler(request),
                command=Command(update=update),
            )

        response = await handler(request)
        if (getattr(request, "state", None) or {}).get("mcp_tool_names"):
            return ExtendedModelResponse(model_response=response, command=Command(update={"mcp_tool_names": []}))
        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ):
        thread_id = request.runtime.execution_info.thread_id
        progress_callback = self._build_progress_callback(request.tool_call["id"])
        cached_resources = self._mcp_resources_by_thread_id.get(thread_id)
        mcp_config = self._resolve_mcp_config(request)
        if cached_resources is not None and cached_resources[0] != mcp_config:
            self._mcp_resources_by_thread_id.pop(thread_id, None)
            cached_resources = None
        if (cached_resources or mcp_config) and not await self._can_use_mcp(request):
            return await handler(request)
        if cached_resources is not None:
            _, tools = cached_resources
            if tools:
                tool_name_map = {tool.name: tool for tool in tools}
                tool_name = request.tool_call["name"]
                logger.info("MCP 会话缓存命中: thread_id={}, tool_name={}", thread_id, tool_name)
                if tool_name in tool_name_map:
                    tool = tool_name_map[tool_name]
                    result = await tool.ainvoke(
                        request.tool_call["args"],
                        config={
                            "metadata": {
                                "mcp_meta": {"userId": (getattr(request, "state", {}) or {}).get("user_id", "default")},
                                "mcp_progress_callback": progress_callback,
                            }
                        },
                    )
                    return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
            else:
                self._mcp_resources_by_thread_id.pop(thread_id, None)

        if mcp_config:
            header_info = self._prepare_mcp_request_headers(request)
            connection_config = self._inject_context_headers(
                mcp_config,
                header_info=header_info,
            )
            tools = await self.get_mcp_tools(connection_config)
            if tools:
                self._mcp_resources_by_thread_id[thread_id] = (mcp_config, tools)
            tool_name_map = {tool.name: tool for tool in tools}
            tool_name = request.tool_call["name"]
            if tool_name in tool_name_map:
                tool = tool_name_map[tool_name]
                result = await tool.ainvoke(
                    request.tool_call["args"],
                    config={
                        "metadata": {
                            "mcp_meta": {"userId": (getattr(request, "state", {}) or {}).get("user_id", "default")},
                            "mcp_progress_callback": progress_callback,
                        }
                    },
                )
                return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        return await handler(request)


if __name__ == "__main__":
    """验证环境变量 MCP_CONFIG 是否生效，并实际加载 MCP 工具。"""

    import asyncio

    async def _load_and_report(middleware: MCPMiddleware, normalized: dict[str, Any]) -> None:
        """加载 MCP 工具并打印加载结果。

        Args:
            middleware: MCP 中间件实例。
            normalized: 归一化后的 MCP 配置。
        """
        tools = await middleware.get_mcp_tools(normalized)
        print(f"\n=== 加载结果: 共 {len(tools)} 个工具 ===")
        for tool in tools:
            print(f"  - {tool.name}")

    print("=== settings.MCP_CONFIG ===")
    print(json.dumps(settings.MCP_CONFIG, ensure_ascii=False, indent=2))

    middleware = MCPMiddleware()
    if not middleware.mcp_config:
        print("\n[结果] MCP_CONFIG 环境变量未生效，settings.MCP_CONFIG 为空")
        raise SystemExit(1)

    normalized = middleware.normalize_mcp_config(middleware.mcp_config)
    print("\n=== MCP 服务列表 ===")
    for name, cfg in normalized["mcpServers"].items():
        print(f"  - {name}: type={cfg.get('type')}, url={cfg.get('url')}")

    asyncio.run(_load_and_report(middleware, normalized))
