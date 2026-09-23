"""模型工厂相关工具。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages.ai import AIMessageChunk
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from deepclaw.settings import settings


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


def get_chat_model(tags: list[str] | None = None) -> ChatOpenAI:
    """创建聊天模型实例。

    Args:
        tags: 模型调用标签，未传时默认为 agent。

    Returns:
        配置当前 OpenAI 兼容接口的聊天模型。
    """
    return ReasoningChatOpenAI(
        model=settings.CHAT_MODEL_NAME,
        base_url=settings.OPENAI_API_BASE,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
        tags=tags or ["agent"],
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "tool_choice": "auto",
            "thinking": {"type": "disabled"},
        },
    )


def get_embedding_model() -> OpenAIEmbeddings:
    """创建向量模型实例。

    Args:
        无额外参数。
    """

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL_NAME,
    )
