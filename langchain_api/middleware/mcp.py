from typing import NotRequired

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

    async def get_mcp_tools(self, mcp_config):
        return await load_langchain_tools_from_mcp_config(
            mcp_config,
            server_name="math",
            tool_name_prefix=False,
        )

    async def awrap_model_call(self, request, handler):
        mcp_config = request.runtime.context.mcp_config
        if mcp_config:
            current_tools = request.tools
            tools = await self.get_mcp_tools(mcp_config)
            mcp_tool_names = [tool.name for tool in tools]
            logger.info(f"加载新的MCP工具名称: {mcp_tool_names}")
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
