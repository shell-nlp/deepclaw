from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ExtendedModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from loguru import logger

from langchain_api.agent.context import AgentContext
from mcp2tool.fastmcp_to_langchain import load_langchain_tools_from_mcp_config


class StateSchema(AgentState):
    mcp_tool_names: NotRequired[list[str]]


class MCPMiddleware(AgentMiddleware[None, AgentContext, None]):
    """MCP 中间件，用于处理 MCP 相关相关的逻辑"""

    state_schema = StateSchema

    def get_mcp_server_names(self, mcp_config: dict[str, Any]) -> list[str]:
        server_root = mcp_config.get("mcpServers")
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

    def get_mcp_server_config(
        self, mcp_config: dict[str, Any], server_name: str
    ) -> dict[str, Any]:
        server_root = mcp_config.get("mcpServers")
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
            tools = await load_langchain_tools_from_mcp_config(
                mcp_config,
                server_name=server_name,
                tool_name_prefix=tool_name_prefix,
            )
            logger.info(
                "MCP 服务加载成功: server_name={}, transport={}, url={}, tool_count={}",
                server_name,
                server_config.get("type"),
                server_config.get("url"),
                len(tools),
            )
            return tools
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
        if not isinstance(mcp_config, dict):
            raise TypeError("`mcp_config` 必须是对象")

        server_names = self.get_mcp_server_names(mcp_config)
        tools = []
        for server_name in server_names:
            tools.extend(
                await self.load_mcp_tools_for_server(
                    mcp_config,
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
                    mcp_config,
                    server_name,
                    tool_name_prefix=True,
                )
            )
        return prefixed_tools

    async def awrap_model_call(self, request, handler):
        mcp_config = request.runtime.context.mcp_config
        if mcp_config:
            current_tools = request.tools
            tools = await self.get_mcp_tools(mcp_config)
            mcp_tool_names = [tool.name for tool in tools]
            if mcp_tool_names:
                logger.info(f"加载新的MCP工具名称: {mcp_tool_names}")
            else:
                logger.warning("MCP 已启用，但当前没有成功加载任何工具，将回退为无 MCP 工具继续对话")
            request = request.override(tools=current_tools + tools)
            update = {"mcp_tool_names": mcp_tool_names}
            return ExtendedModelResponse(
                model_response=await handler(request),
                command=Command(update=update),
            )

        return await handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ):
        mcp_config = request.runtime.context.mcp_config
        if mcp_config:
            tools = await self.get_mcp_tools(mcp_config)
            tool_name_map = {tool.name: tool for tool in tools}
            tool_name = request.tool_call["name"]
            if tool_name in tool_name_map:
                tool = tool_name_map[tool_name]
                result = await tool.ainvoke(
                    request.tool_call["args"],
                    config={
                        "metadata": {
                            "mcp_meta": {"userId": request.runtime.context.user_id}
                        }
                    },
                )
                return ToolMessage(content=result, tool_call_id=request.tool_call["id"])
        return await handler(request)
