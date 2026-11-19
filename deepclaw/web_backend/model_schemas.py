from typing import Literal

from pydantic import BaseModel, Field


class ModelItemResponse(BaseModel):
    """模型目录中的单个模型响应。"""

    id: str
    type: Literal["chat", "embedding"]
    name: str
    provider: str
    api_base: str
    api_key: None = None
    api_key_masked: str
    has_api_key: bool
    context_window: int | None
    created_at: str
    updated_at: str
    active: bool


class ModelCatalogResponse(BaseModel):
    """按模型用途分组的模型目录响应。"""

    chat_models: list[ModelItemResponse]
    embedding_models: list[ModelItemResponse]
    active_chat_model_id: str | None
    active_embedding_model_id: str | None


class ModelCreateRequest(BaseModel):
    """创建模型请求。

    Args:
        type: 模型用途，chat 为大模型，embedding 为语义模型。
        name: 模型名称或模型服务 ID。
        provider: 服务提供方。
        api_base: OpenAI 兼容接口地址。
        api_key: 服务密钥。
        context_window: 大模型上下文窗口。
    """

    type: Literal["chat", "embedding"]
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(default="OpenAI Compatible", max_length=100)
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    context_window: int | None = Field(default=128_000, ge=1, le=10_000_000)


class ModelUpdateRequest(BaseModel):
    """更新模型请求，空 API Key 表示保留原密钥。"""

    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(default="OpenAI Compatible", max_length=100)
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2_000)
    context_window: int | None = Field(default=128_000, ge=1, le=10_000_000)


class ModelActivateRequest(BaseModel):
    """切换当前活动模型请求。"""

    type: Literal["chat", "embedding"]


class ModelTestResponse(BaseModel):
    """模型连通性测试结果。"""

    ok: bool
    message: str
    latency_ms: int
    dimension: int | None = None
