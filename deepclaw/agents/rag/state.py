from typing import NotRequired

from langchain.agents.middleware import AgentState


class StateSchema(AgentState):
    """RAG Agent 的 AG-UI 可持久化运行状态。"""

    # 当前用户标识，由路由层写入可信值。
    user_id: NotRequired[str]
    # 知识库 passage 索引名称。
    index_name: NotRequired[str]
    # 知识图谱索引前缀。
    graph_name: NotRequired[str]
    # 是否启用联网搜索。
    internet_search: NotRequired[bool]
    # 是否启用深度思考。
    deep_thinking: NotRequired[bool]
    # 透传给下游请求的 HTTP 请求头。
    header_info: NotRequired[dict[str, str]]
