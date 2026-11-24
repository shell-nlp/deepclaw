"""运行期模型目录的持久化、迁移与当前模型应用。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from deepclaw.constant import HOME_PATH
from deepclaw.settings import settings

MODEL_CONFIG_FILENAME = "model_config.json"
MODEL_CONFIG_PATH = HOME_PATH / MODEL_CONFIG_FILENAME
KEYLESS_API_KEY = "deepclaw-no-key"
ModelType = Literal["chat", "embedding"]
ChatUpstreamFormat = Literal["chat_completions", "responses"]
ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
DEFAULT_CHAT_UPSTREAM_FORMAT: ChatUpstreamFormat = "chat_completions"
active_chat_headers: dict[str, str] = {}
active_chat_upstream_format: ChatUpstreamFormat = DEFAULT_CHAT_UPSTREAM_FORMAT
active_embedding_options: dict[str, Any] = {}


def _now() -> str:
    """返回模型目录记录使用的 UTC 时间文本。

    Returns:
        ISO 8601 格式的 UTC 时间。
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_model(
    model_type: ModelType,
    name: str,
    provider: str,
    api_base: str,
    api_key: str,
    context_window: int,
) -> dict[str, Any]:
    """创建一个模型目录记录。

    Args:
        model_type: 大模型或语义模型类型。
        name: 模型标识。
        provider: 服务提供方名称。
        api_base: OpenAI 兼容网关地址。
        api_key: 服务密钥。
        context_window: 大模型上下文窗口。

    Returns:
        新模型记录。
    """
    timestamp = _now()
    return {
        "id": uuid.uuid4().hex,
        "type": model_type,
        "name": name.strip(),
        "provider": provider.strip() or "OpenAI Compatible",
        "api_base": api_base.rstrip("/"),
        "api_key": api_key,
        "context_window": context_window if model_type == "chat" else None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

def _legacy_state(payload: dict[str, Any]) -> dict[str, Any] | None:
    """把旧版单模型配置迁移为模型目录。

    Args:
        payload: 旧版配置内容。

    Returns:
        迁移后的目录状态；无法识别时返回 None。
    """
    if "models" in payload:
        return None
    chat_name = str(payload.get("CHAT_MODEL_NAME") or settings.CHAT_MODEL_NAME)
    embedding_name = str(payload.get("EMBEDDING_MODEL_NAME") or settings.EMBEDDING_MODEL_NAME)
    api_base = str(payload.get("OPENAI_API_BASE") or settings.OPENAI_API_BASE)
    api_key = str(payload.get("OPENAI_API_KEY") or settings.OPENAI_API_KEY)
    context = int(payload.get("MODEL_CONTEXT_WINDOW") or settings.MODEL_CONTEXT_WINDOW)
    chat = _new_model("chat", chat_name, "OpenAI Compatible", api_base, api_key, context)
    embedding = _new_model("embedding", embedding_name, "OpenAI Compatible", api_base, api_key, context)
    return {
        "models": [chat, embedding],
        "active_chat_model_id": chat["id"],
        "active_embedding_model_id": embedding["id"],
    }


def _default_state() -> dict[str, Any]:
    """根据环境变量生成初始模型目录。

    未在环境变量中配置任何模型时返回空目录，模型改由前端模型目录添加。

    Returns:
        包含一个大模型和一个语义模型的目录状态；环境变量为空时返回空目录。
    """
    if not any(
        (
            settings.CHAT_MODEL_NAME,
            settings.EMBEDDING_MODEL_NAME,
            settings.OPENAI_API_BASE,
            settings.OPENAI_API_KEY,
        )
    ):
        return {"models": [], "active_chat_model_id": None, "active_embedding_model_id": None}
    return _legacy_state({}) or {"models": [], "active_chat_model_id": None, "active_embedding_model_id": None}


def load_initial_model_state() -> dict[str, Any]:
    """读取待导入的旧目录，缺少文件时从环境变量初始化。

    Args:
        无。
    """
    try:
        legacy_bytes = MODEL_CONFIG_PATH.read_bytes()
        payload = json.loads(legacy_bytes)
    except FileNotFoundError:
        return _default_state()
    if isinstance(payload, dict) and "models" not in payload:
        payload = _legacy_state(payload) or _default_state()
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("旧模型目录格式无效，无法导入。")
    payload["models"] = [item for item in payload["models"] if isinstance(item, dict) and item.get("id")]
    for model_type in ("chat", "embedding"):
        payload.setdefault(
            f"active_{model_type}_model_id",
            next((model["id"] for model in payload["models"] if model.get("type") == model_type), None),
        )
    payload["legacy_import_sha256"] = hashlib.sha256(legacy_bytes).hexdigest()
    return payload


def remove_imported_model_file(digest: str | None) -> None:
    """仅清理已成功入库且内容未变的旧配置文件。

    Args:
        digest: 数据库中记录的导入文件摘要。
    """
    if digest:
        try:
            if hashlib.sha256(MODEL_CONFIG_PATH.read_bytes()).hexdigest() == digest:
                MODEL_CONFIG_PATH.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def apply_active_model_config(state: dict[str, Any]) -> None:
    """把目录中的当前模型应用到进程 Settings。

    Args:
        state: 模型目录状态。
    """
    global active_chat_headers, active_chat_upstream_format, active_embedding_options
    models = state.get("models", [])
    active_chat = next((m for m in models if m.get("id") == state.get("active_chat_model_id")), None)
    active_embedding = next((m for m in models if m.get("id") == state.get("active_embedding_model_id")), None)
    active_chat_headers = dict(active_chat.get("request_headers", {})) if active_chat else {}
    active_chat_upstream_format = (
        "responses" if active_chat and active_chat.get("upstream_format") == "responses"
        else DEFAULT_CHAT_UPSTREAM_FORMAT
    )
    active_embedding_options = (
        {
            "base_url": active_embedding["api_base"],
            "api_key": active_embedding.get("api_key") or KEYLESS_API_KEY,
            "default_headers": dict(active_embedding.get("request_headers", {})),
        }
        if active_embedding else {}
    )
    if active_chat:
        settings.OPENAI_API_BASE = active_chat.get("api_base", settings.OPENAI_API_BASE)
        settings.OPENAI_API_KEY = active_chat.get("api_key", settings.OPENAI_API_KEY)
        settings.CHAT_MODEL_NAME = active_chat.get("name", settings.CHAT_MODEL_NAME)
        settings.MODEL_CONTEXT_WINDOW = int(active_chat.get("context_window") or settings.MODEL_CONTEXT_WINDOW)
    if active_embedding:
        settings.EMBEDDING_MODEL_NAME = active_embedding.get("name", settings.EMBEDDING_MODEL_NAME)


def mask_api_key(api_key: str | None) -> str:
    """生成 API Key 的安全展示文本。

    Args:
        api_key: 原始 API Key。

    Returns:
        脱敏后的 API Key。
    """
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}••••{api_key[-4:]}"


def public_model(model: dict[str, Any], active_id: str | None) -> dict[str, Any]:
    """生成不包含密钥原文的模型响应。

    Args:
        model: 内部模型记录。
        active_id: 当前类型的活动模型 ID。

    Returns:
        脱敏后的模型记录。
    """
    return {
        **model,
        "api_key": None,
        "api_key_masked": mask_api_key(model.get("api_key")),
        "has_api_key": bool(model.get("api_key")),
        "request_headers": list(model.get("request_headers", {})),
        "reasoning_efforts": model.get("reasoning_efforts", []) if model["type"] == "chat" else [],
        "upstream_format": (
            model.get("upstream_format") or DEFAULT_CHAT_UPSTREAM_FORMAT
            if model["type"] == "chat" else None
        ),
        "active": model.get("id") == active_id,
    }
