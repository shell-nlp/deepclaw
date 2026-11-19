from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request

from deepclaw.model_config import (
    load_persisted_model_config,
    mask_api_key,
    persist_model_config,
)
from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import require_permission
from deepclaw.web_backend.model_schemas import ModelConfigResponse, ModelConfigUpdateRequest

router = APIRouter(prefix="/api/models", tags=["models"])


def _current_response() -> ModelConfigResponse:
    """构造当前模型配置响应。

    Returns:
        ModelConfigResponse: 脱敏后的模型配置。
    """
    persisted = load_persisted_model_config()
    api_key = str(getattr(settings, "OPENAI_API_KEY", "") or "")
    return ModelConfigResponse(
        api_base=settings.OPENAI_API_BASE,
        api_key_masked=mask_api_key(api_key),
        has_api_key=bool(api_key),
        chat_model_name=settings.CHAT_MODEL_NAME,
        embedding_model_name=settings.EMBEDDING_MODEL_NAME,
        model_context_window=settings.MODEL_CONTEXT_WINDOW,
        source="saved" if persisted else "environment",
    )


@router.get("/config", response_model=ModelConfigResponse, summary="查询模型配置")
async def get_model_config(
    actor: CurrentActor = Depends(require_permission("/api/models/config", "read")),
) -> ModelConfigResponse:
    """返回当前模型配置，不暴露 API Key 原文。"""
    return _current_response()


@router.put("/config", response_model=ModelConfigResponse, summary="保存模型配置")
async def update_model_config(
    request: ModelConfigUpdateRequest,
    http_request: Request,
    actor: CurrentActor = Depends(require_permission("/api/models/config", "write")),
) -> ModelConfigResponse:
    """保存模型配置并清理智能体运行时缓存。

    Args:
        request: 新的模型配置。
        http_request: 当前 HTTP 请求，用于访问应用状态。
        actor: 当前管理员主体。

    Returns:
        ModelConfigResponse: 保存后的脱敏配置。

    Raises:
        HTTPException: API 地址不是合法 HTTP(S) 地址时抛出。
    """
    parsed = urlparse(request.api_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="API 地址必须是合法的 http 或 https URL。")

    current_key = str(getattr(settings, "OPENAI_API_KEY", "") or "")
    next_key = current_key if request.api_key is None or not request.api_key.strip() else request.api_key.strip()
    config = {
        "OPENAI_API_BASE": request.api_base.rstrip("/"),
        "OPENAI_API_KEY": next_key,
        "CHAT_MODEL_NAME": request.chat_model_name.strip(),
        "EMBEDDING_MODEL_NAME": request.embedding_model_name.strip(),
        "MODEL_CONTEXT_WINDOW": request.model_context_window,
    }
    persist_model_config(config)
    runtime_cache = getattr(http_request.app.state, "agent_runtime_cache", None)
    if runtime_cache is not None:
        await runtime_cache.close()
    return _current_response()
