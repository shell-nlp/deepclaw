from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """都是在一次请求中不会改变的上下文"""

    # 用户ID，用于标识用户
    user_id: str = Field("default", description="用户ID")
    # 是否启用联网搜索
    internet_search: bool = Field(False, description="是否启用联网搜索")
    # 是否启用深度思考
    deep_thinking: bool = Field(False, description="是否启用深度思考")
    # MCP 配置
    mcp_config: dict | None = Field(None, description="MCP 配置")
    # 当前请求的原始 HTTP 请求头
    header_info: dict | None = Field(default_factory=dict, description="请求头信息")
