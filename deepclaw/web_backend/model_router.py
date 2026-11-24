import re
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from openai import APIConnectionError, APIStatusError, APITimeoutError

from deepclaw.model_config import (
    KEYLESS_API_KEY,
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
    ModelDraftTestRequest,
    ModelHeaderRequest,
    ModelItemResponse,
    ModelSecretResponse,
    ModelTestResponse,
    ModelUpdateRequest,
)

router = APIRouter(prefix="/api/models", tags=["models"])
HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
RESERVED_HEADERS = {
    "connection", "content-length", "expect", "host", "keep-alive",
    "proxy-authorization", "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
}


def _find_model(state: dict, model_id: str) -> dict:
    """查找模型记录，不存在时返回 404。

    Args:
        state: 模型目录。
        model_id: 模型标识。
    """
    model = next((item for item in state.get("models", []) if item.get("id") == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在。")
    return model


def _resolve_headers(rows: list[ModelHeaderRequest] | None, saved: dict[str, str]) -> dict[str, str]:
    """校验并合并编辑表单中的请求头。

    Args:
        rows: 表单中的请求头，省略时保留原配置。
        saved: 已保存的请求头。
    """
    if rows is None:
        return saved
    if len(rows) > 32:
        raise HTTPException(status_code=422, detail="最多可设置 32 条请求头。")
    previous = {name.lower(): value for name, value in saved.items()}
    seen: set[str] = set()
    headers = {}
    for index, row in enumerate(rows, start=1):
        name = row.name.strip()
        key = name.lower()
        value = previous.get(key) if row.value is None else row.value.strip(" \t")
        if not HEADER_NAME.fullmatch(name) or len(name) > 128 or key in RESERVED_HEADERS:
            raise HTTPException(status_code=422, detail=f"第 {index} 条请求头名称无效或为保留名称。")
        if key in seen:
            raise HTTPException(status_code=422, detail=f"第 {index} 条请求头名称重复。")
        if not value or len(value) > 8192 or not re.fullmatch(r"[\x20-\x7e\t]+", value):
            raise HTTPException(status_code=422, detail=f"第 {index} 条请求头需要有效的 ASCII 值。")
        seen.add(key)
        headers[name.title()] = value
    return headers


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
    try:
        parsed = urlparse(normalized)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname and not (
            parsed.username is not None or parsed.query or parsed.fragment
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=422, detail="API 地址必须是合法的 http 或 https URL。")
    return normalized


async def _reset_runtime(http_request: Request) -> None:
    """清理应用中的智能体缓存，使活动模型立即生效。

    Args:
        http_request: 当前 HTTP 请求。
    """
    from deepclaw.tools import retriever

    retriever.default_retriever = None
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
    model["request_headers"] = _resolve_headers(request.request_headers, {})
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
    return await _probe_model(_find_model(load_model_state(), model_id))


@router.post("/test-draft", response_model=ModelTestResponse, summary="测试当前表单配置")
async def test_model_draft(
    request: ModelDraftTestRequest,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelTestResponse:
    """直接试连表单配置，复用未修改的已保存凭据。

    Args:
        request: 当前表单及可选的原模型标识。
        actor: 具备模型写权限的用户。
    """
    saved = _find_model(load_model_state(), request.model_id) if request.model_id else {}
    if saved and saved["type"] != request.type:
        raise HTTPException(status_code=422, detail="模型类型与原配置不符。")
    return await _probe_model({
        "type": request.type,
        "name": request.name.strip(),
        "api_base": _validate_api_base(request.api_base),
        "api_key": (request.api_key or "").strip() or saved.get("api_key", ""),
        "request_headers": _resolve_headers(request.request_headers, saved.get("request_headers", {})),
    })


@router.post("/{model_id}/reveal-key", response_model=ModelSecretResponse, summary="查看模型密钥")
async def reveal_model_key(
    model_id: str,
    response: Response,
    actor: CurrentActor = Depends(require_permission("/api/models", "write")),
) -> ModelSecretResponse:
    """仅在有模型写权限的用户主动查看时返回密钥。

    Args:
        model_id: 模型标识。
        response: 禁止缓存的 HTTP 响应。
        actor: 具备模型写权限的用户。
    """
    response.headers["Cache-Control"] = "no-store"
    model = _find_model(load_model_state(), model_id)
    return ModelSecretResponse(api_key=model.get("api_key", ""))


async def _probe_model(model: dict) -> ModelTestResponse:
    """验证上游模型是否能完成一次短请求，并返回耗时。

    Args:
        model: 包含目标地址、模型与凭据的配置。
    """
    started = time.perf_counter()
    options = {
        "model": model["name"],
        "base_url": model["api_base"],
        "api_key": model.get("api_key") or KEYLESS_API_KEY,
        "default_headers": model.get("request_headers", {}),
        "timeout": 20,
        "max_retries": 0,
    }
    try:
        if model.get("type") == "chat":
            from langchain_openai import ChatOpenAI
            await ChatOpenAI(**options).ainvoke("请只回复 OK")
            result_message = "模型可用"
            dimension = None
        else:
            from langchain_openai import OpenAIEmbeddings
            vector = await OpenAIEmbeddings(**options, check_embedding_ctx_length=False).aembed_query("DeepClaw 模型连通性测试")
            result_message = "连接成功，已生成语义向量"
            dimension = len(vector)
        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
        return ModelTestResponse(ok=True, message=result_message, latency_ms=latency_ms, dimension=dimension)
    except Exception as exc:  # noqa: BLE001 - 测试接口需要返回可读业务错误
        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
        if isinstance(exc, APITimeoutError):
            detail = "模型响应超时，请稍后重试。"
        elif isinstance(exc, APIConnectionError):
            detail = "无法连接模型服务，请检查地址和网络。"
        elif isinstance(exc, APIStatusError):
            hints = {
                401: "请检查 API Key 和请求头",
                403: "请检查模型访问权限和请求头",
                404: "请检查 API 地址和模型名称",
                429: "请检查调用额度或稍后重试",
            }
            detail = f"服务返回 HTTP {exc.status_code}，{hints.get(exc.status_code, '请检查模型服务配置')}。"
        else:
            detail = "未收到有效模型响应，请检查模型配置。"
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
    model["request_headers"] = _resolve_headers(request.request_headers, model.get("request_headers", {}))
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
