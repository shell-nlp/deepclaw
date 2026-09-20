from typing import Any, NotRequired

from langchain.agents.middleware import AgentState


class StateSchema(AgentState):
    """通用 Agent 的 AG-UI 可持久化运行状态。"""

    user_id: NotRequired[str]
    internet_search: NotRequired[bool]
    deep_thinking: NotRequired[bool]
    mcp_config: NotRequired[dict[str, Any] | None]
    header_info: NotRequired[dict[str, str]]
    mcp_tool_names: NotRequired[list[str]]
