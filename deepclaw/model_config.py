"""运行期模型配置的本地持久化与脱敏辅助。"""

from __future__ import annotations

import json
import os
from typing import Any

from deepclaw.constant import HOME_PATH
from deepclaw.settings import settings

MODEL_CONFIG_FILENAME = "model_config.json"
MODEL_CONFIG_PATH = HOME_PATH / MODEL_CONFIG_FILENAME
MODEL_CONFIG_KEYS = (
    "OPENAI_API_BASE",
    "OPENAI_API_KEY",
    "CHAT_MODEL_NAME",
    "EMBEDDING_MODEL_NAME",
    "MODEL_CONTEXT_WINDOW",
)


def load_persisted_model_config() -> dict[str, Any]:
    """读取本地持久化的模型配置。

    Args:
        无。

    Returns:
        经过字段过滤的模型配置；文件不存在或内容损坏时返回空字典。
    """
    try:
        with MODEL_CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in MODEL_CONFIG_KEYS if key in payload}


def apply_model_config(config: dict[str, Any]) -> None:
    """把模型配置应用到当前进程的 Settings 对象。

    Args:
        config: 已校验的模型配置字段。
    """
    for key in MODEL_CONFIG_KEYS:
        if key in config:
            setattr(settings, key, config[key])


def persist_model_config(config: dict[str, Any]) -> dict[str, Any]:
    """原子写入模型配置并立即应用到当前进程。

    Args:
        config: 已校验的完整模型配置。

    Returns:
        实际写入的模型配置。
    """
    HOME_PATH.mkdir(parents=True, exist_ok=True)
    normalized = {key: config[key] for key in MODEL_CONFIG_KEYS if key in config}
    temporary_path = MODEL_CONFIG_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, MODEL_CONFIG_PATH)
    apply_model_config(normalized)
    return normalized


def mask_api_key(api_key: str | None) -> str:
    """生成 API Key 的安全展示文本。

    Args:
        api_key: 原始 API Key。

    Returns:
        脱敏后的 API Key；空值返回空字符串。
    """
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}••••{api_key[-4:]}"


apply_model_config(load_persisted_model_config())
