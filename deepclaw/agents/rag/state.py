from typing import NotRequired

from langchain.agents.middleware import AgentState


class StateSchema(AgentState):
    """RAG Agent 的 AG-UI 可持久化运行状态。"""

    user_id: NotRequired[str]
    index_name: NotRequired[str]
    graph_name: NotRequired[str]
    internet_search: NotRequired[bool]
    deep_thinking: NotRequired[bool]
    header_info: NotRequired[dict[str, str]]
