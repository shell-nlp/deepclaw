from typing import Any, NotRequired

from langchain.agents.middleware import AgentState


class StateSchema(AgentState):
    """通用 Agent 的 AG-UI 可持久化运行状态。"""

    # 当前用户标识，由路由层写入可信值。
    user_id: NotRequired[str]
    # 是否启用联网搜索。
    internet_search: NotRequired[bool]
    # 是否启用深度思考。
    deep_thinking: NotRequired[bool]
    # 本次请求使用的 MCP 配置。
    mcp_config: NotRequired[dict[str, Any] | None]
    # 透传给下游请求的 HTTP 请求头。
    header_info: NotRequired[dict[str, str]]
    # 当前已加载的 MCP 工具名称。
    mcp_tool_names: NotRequired[list[str]]
