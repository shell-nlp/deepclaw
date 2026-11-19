from pydantic import BaseModel, Field


class ModelConfigResponse(BaseModel):
    """模型配置响应，API Key 只返回脱敏信息。"""

    api_base: str
    api_key_masked: str
    has_api_key: bool
    chat_model_name: str
    embedding_model_name: str
    model_context_window: int
    source: str


class ModelConfigUpdateRequest(BaseModel):
    """模型配置更新请求。

    Args:
        api_base: OpenAI 兼容接口地址。
        api_key: API Key；留空表示保留当前值。
        chat_model_name: 聊天模型名称。
        embedding_model_name: 向量模型名称。
        model_context_window: 模型上下文窗口。
    """

    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    chat_model_name: str = Field(min_length=1, max_length=200)
    embedding_model_name: str = Field(min_length=1, max_length=200)
    model_context_window: int = Field(default=128_000, ge=1, le=10_000_000)


class ModelConfigTestRequest(BaseModel):
    """模型连接测试请求。"""

    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    chat_model_name: str = Field(min_length=1, max_length=200)
