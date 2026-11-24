"""模型工厂相关工具。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from langchain_core.messages.ai import AIMessageChunk
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from deepclaw.settings import settings

# 兼容网关关闭思考的统一参数：只传 enable_thinking 不足以关闭，必须同时给 thinking。
DISABLE_THINKING_EXTRA_BODY: dict[str, Any] = {
    "chat_template_kwargs": {"enable_thinking": False},
    "thinking": {"type": "disabled"},
}
RUN_CHAT_MODEL: ContextVar[ChatOpenAI | None] = ContextVar("run_chat_model", default=None)


class ReasoningChatOpenAI(ChatOpenAI):
    """在 ChatOpenAI 上补抓兼容接口的流式 reasoning_content。

    Args:
        与 ChatOpenAI 一致。
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None = None,
    ):
        """转换流式 chunk，并保留兼容接口的思考内容。

        Args:
            chunk: 原始 OpenAI 兼容流式 chunk。
            default_chunk_class: LangChain 默认生成块类型。
            base_generation_info: 基础生成信息。

        Returns:
            转换后的生成块；无有效生成块时返回 None。
        """
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation_chunk is None:
            return None
        delta = _delta_of(chunk)
        if delta:
            piece = delta.get("reasoning_content")
            if piece is None:
                piece = delta.get("reasoning")
            if piece is not None:
                message = generation_chunk.message
                if isinstance(message, AIMessageChunk):
                    text = str(piece or "")
                    if text:
                        message.additional_kwargs["reasoning_content"] = text
        return generation_chunk


def _delta_of(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """提取 OpenAI 兼容流式 chunk 的 delta。

    Args:
        chunk: 原始 OpenAI 兼容流式 chunk。

    Returns:
        首个 choice 的 delta；不存在时返回 None。
    """
    choices = chunk.get("choices") or []
    if choices:
        delta = (choices[0] or {}).get("delta")
        return delta if isinstance(delta, dict) else None
    inner = (chunk.get("chunk") or {}).get("choices") or []
    if inner:
        delta = (inner[0] or {}).get("delta")
        return delta if isinstance(delta, dict) else None
    return None


def get_chat_model(tags: list[str] | None = None, *, catalog_model: dict[str, Any] | None = None) -> ChatOpenAI:
    """创建聊天模型实例。

    Args:
        tags: 模型调用标签，未传时默认为 agent。
        catalog_model: 本轮选择的模型记录，未传时使用系统默认模型。

    Returns:
        配置当前 OpenAI 兼容接口的聊天模型。
    """
    from deepclaw import model_config

    selected = catalog_model or {}
    return ReasoningChatOpenAI(
        model=selected.get("name", settings.CHAT_MODEL_NAME),
        base_url=selected.get("api_base", settings.OPENAI_API_BASE),
        api_key=selected.get("api_key", settings.OPENAI_API_KEY) or model_config.KEYLESS_API_KEY,
        default_headers=selected.get("request_headers", {}) if selected else model_config.active_chat_headers,
        streaming=True,
        stream_usage=True,
        tags=tags or ["agent"],
        profile={"max_input_tokens": selected.get("context_window") or settings.MODEL_CONTEXT_WINDOW},
        extra_body={
            **DISABLE_THINKING_EXTRA_BODY,
            "tool_choice": "auto",
        },
    )


def get_embedding_model() -> OpenAIEmbeddings:
    """创建向量模型实例。

    Args:
        无额外参数。
    """

    from deepclaw import model_config

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL_NAME,
        **model_config.active_embedding_options,
    )
