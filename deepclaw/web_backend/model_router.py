import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request

from deepclaw.model_config import (
    _new_model,
    load_model_state,
    persist_model_state,
    public_model,
)
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import require_permission
from deepclaw.web_backend.model_schemas import (
    ModelActivateRequest,
    ModelCatalogResponse,
    ModelCreateRequest,
    ModelItemResponse,
    ModelTestResponse,
    ModelUpdateRequest,
)

router = APIRouter(prefix="/api/models", tags=["models"])


def _catalog_response(state: dict) -> ModelCatalogResponse:
    """构造按用途分组的模型目录响应。

    Args:
        state: 当前模型目录状态。

    Returns:
        ModelCatalogResponse: 脱敏后的模型目录。
    """
    models = state.get("models", [])
    chat_active = state.get("active_chat_model_id")
    embedding_active = state.get("active_embedding_model_id")
    chat_models = [public_model(model, chat_active) for model in models if model.get("type") == "chat"]
    embedding_models = [public_model(model, embedding_active) for model in models if model.get("type") == "embedding"]
    return ModelCatalogResponse(
        chat_models=[ModelItemResponse(**model) for model in chat_models],
        embedding_models=[ModelItemResponse(**model) for model in embedding_models],
        active_chat_model_id=chat_active,
        active_embedding_model_id=embedding_active,
    )


def _validate_api_base(api_base: str) -> str:
    """校验并标准化 OpenAI 兼容接口地址。

    Args:
        api_base: 待校验地址。

    Returns:
        去掉末尾斜杠的地址。

    Raises:
        HTTPException: 地址不是合法 HTTP(S) URL 时抛出。
    """
    normalized = api_base.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="API 地址必须是合法的 http 或 https URL。")
    return normalized


async def _reset_runtime(http_request: Request) -> None:
    """清理应用中的智能体缓存，使活动模型立即生效。

    Args:
        http_request: 当前 HTTP 请求。
    """
    runtime_cache = getattr(http_request.app.state, "agent_runtime_cache", None)
    if runtime_cache is not None:
        await runtime_cache.close()


@router.get("/catalog", response_model=ModelCatalogResponse, summary="查询模型目录")
async def get_model_catalog(
    actor: CurrentActor = Depends(require_permission("/api/models/catalog", "read")),
) -> ModelCatalogResponse:
    """返回大模型与语义模型目录。"""
    return _catalog_response(load_model_state())


@router.post("", response_model=ModelCatalogResponse, summary="新建模型")
async def create_model(
    request: ModelCreateRequest,
    http_request: Request,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelCatalogResponse:
    """新建模型并在该类型尚无活动模型时自动启用。"""
    api_base = _validate_api_base(request.api_base)
    state = load_model_state()
    model = _new_model(
        request.type,
        request.name,
        request.provider,
        api_base,
        request.api_key or "",
        request.context_window or 128_000,
    )
    state.setdefault("models", []).append(model)
    active_key = "active_chat_model_id" if request.type == "chat" else "active_embedding_model_id"
    if not state.get(active_key):
        state[active_key] = model["id"]
    persist_model_state(state)
    await _reset_runtime(http_request)
    return _catalog_response(state)


@router.post("/{model_id}/test", response_model=ModelTestResponse, summary="测试模型")
async def test_model(
    model_id: str,
    actor: CurrentActor = Depends(require_permission("/api/models", "read")),
) -> ModelTestResponse:
    """调用一次模型服务，验证地址、密钥和模型名称。

    Args:
        model_id: 待测试的模型 ID。
        actor: 当前管理员主体。

    Returns:
        ModelTestResponse: 连通性、耗时和语义向量维度结果。
    """
    state = load_model_state()
    model = next((item for item in state.get("models", []) if item.get("id") == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在。")
    started = time.perf_counter()
    try:
        if model.get("type") == "chat":
            from langchain_openai import ChatOpenAI
            response = await ChatOpenAI(model=model["name"], base_url=model["api_base"], api_key=model.get("api_key", ""), temperature=0, max_tokens=8).ainvoke("请只回复 OK")
            message = str(getattr(response, "content", "") or "").strip()
            result_message = "连接成功" + (("，模型回复：" + message[:40]) if message else "")
            dimension = None
        else:
            from langchain_openai import OpenAIEmbeddings
            vector = await OpenAIEmbeddings(model=model["name"], base_url=model["api_base"], api_key=model.get("api_key", "")).aembed_query("DeepClaw 模型连通性测试")
            result_message = "连接成功，已生成语义向量"
            dimension = len(vector)
        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
        return ModelTestResponse(ok=True, message=result_message, latency_ms=latency_ms, dimension=dimension)
    except Exception as exc:  # noqa: BLE001 - 测试接口需要返回可读业务错误
        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
        detail = str(exc).replace(model.get("api_key", ""), "***")[:300]
        return ModelTestResponse(ok=False, message=f"连接失败：{detail}", latency_ms=latency_ms)


@router.put("/{model_id}", response_model=ModelCatalogResponse, summary="编辑模型")
async def update_model(
    model_id: str,
    request: ModelUpdateRequest,
    http_request: Request,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelCatalogResponse:
    """编辑模型目录中的一条记录。"""
    state = load_model_state()
    model = next((item for item in state.get("models", []) if item.get("id") == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在。")
    model["name"] = request.name.strip()
    model["provider"] = request.provider.strip() or "OpenAI Compatible"
    model["api_base"] = _validate_api_base(request.api_base)
    if request.api_key and request.api_key.strip():
        model["api_key"] = request.api_key.strip()
    if model.get("type") == "chat":
        model["context_window"] = request.context_window or 128_000
    persist_model_state(state)
    await _reset_runtime(http_request)
    return _catalog_response(state)


@router.delete("/{model_id}", response_model=ModelCatalogResponse, summary="删除模型")
async def delete_model(
    model_id: str,
    http_request: Request,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelCatalogResponse:
    """删除模型；当前活动模型不可直接删除。"""
    state = load_model_state()
    model = next((item for item in state.get("models", []) if item.get("id") == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在。")
    active_key = "active_chat_model_id" if model.get("type") == "chat" else "active_embedding_model_id"
    if state.get(active_key) == model_id:
        raise HTTPException(status_code=409, detail="请先切换其他模型，再删除当前活动模型。")
    state["models"] = [item for item in state.get("models", []) if item.get("id") != model_id]
    persist_model_state(state)
    await _reset_runtime(http_request)
    return _catalog_response(state)


@router.post("/{model_id}/activate", response_model=ModelCatalogResponse, summary="启用模型")
async def activate_model(
    model_id: str,
    request: ModelActivateRequest,
    http_request: Request,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelCatalogResponse:
    """切换指定类型的活动模型。"""
    state = load_model_state()
    model = next((item for item in state.get("models", []) if item.get("id") == model_id), None)
    if model is None or model.get("type") != request.type:
        raise HTTPException(status_code=404, detail="指定类型的模型不存在。")
    state["active_chat_model_id" if request.type == "chat" else "active_embedding_model_id"] = model_id
    persist_model_state(state)
    await _reset_runtime(http_request)
    return _catalog_response(state)
