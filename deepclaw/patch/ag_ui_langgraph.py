"""AG-UI LangGraph 适配层补丁。

`ag_ui_langgraph` 在处理 `on_chat_model_stream` 事件时，只要分片携带推理内容
（`additional_kwargs.reasoning_content`）就只发送推理事件并提前返回。部分模型
会把「最后一段推理」和「第一段正文」放进同一个分片，此时正文会被静默丢弃：
短回答会整段丢失，长回答会丢掉开头几个字。这里在图的流式事件上做一次拆分，
把这种分片拆成「纯推理」和「纯正文」两个事件，保证推理与正文都不丢。
"""

import functools
from collections.abc import AsyncIterator
from typing import Any

from ag_ui_langgraph.utils import resolve_message_content, resolve_reasoning_content


_WRAPPER_MARK = "__deepclaw_reasoning_split__"
_REASONING_BLOCK_TYPES = {"thinking", "reasoning", "reasoning_content"}


def _message_text(chunk: Any) -> str:
    """读取模型分片中的正文文本。

    Args:
        chunk: LangChain 模型分片。

    Returns:
        分片中的正文文本；不存在时返回空串。
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return resolve_message_content(content) or ""
    return ""


def _has_reasoning(chunk: Any) -> bool:
    """判断模型分片是否携带推理内容。

    Args:
        chunk: LangChain 模型分片。

    Returns:
        分片包含推理内容时返回 True。
    """
    try:
        return resolve_reasoning_content(chunk) is not None
    except Exception:
        return False


def _drop_message_text(chunk: Any) -> Any:
    """复制分片并清空正文。

    Args:
        chunk: 原始模型分片。

    Returns:
        仅保留推理内容的模型分片。
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        kept = [
            block
            for block in content
            if not (isinstance(block, dict) and block.get("type") == "text")
        ]
        return chunk.model_copy(update={"content": kept})
    return chunk.model_copy(update={"content": ""})


def _drop_reasoning_text(chunk: Any) -> Any:
    """复制分片并移除推理内容。

    Args:
        chunk: 原始模型分片。

    Returns:
        仅保留正文内容的模型分片。
    """
    additional = dict(getattr(chunk, "additional_kwargs", None) or {})
    additional.pop("reasoning_content", None)
    additional.pop("reasoning", None)
    update: dict[str, Any] = {"additional_kwargs": additional}
    content = getattr(chunk, "content", None)
    if isinstance(content, list):
        update["content"] = [
            block
            for block in content
            if not (
                isinstance(block, dict)
                and block.get("type") in _REASONING_BLOCK_TYPES
            )
        ]
    return chunk.model_copy(update=update)


def _replace_chunk(event: dict[str, Any], chunk: Any) -> dict[str, Any]:
    """替换事件中的模型分片。

    Args:
        event: 原始 LangGraph 流式事件。
        chunk: 替换后的模型分片。

    Returns:
        携带新分片的事件副本。
    """
    data = dict(event.get("data") or {})
    data["chunk"] = chunk
    return {**event, "data": data}


async def split_reasoning_text_events(
    stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """拆分同时携带推理与正文的模型分片事件。

    Args:
        stream: LangGraph 原始流式事件。

    Yields:
        拆分后的流式事件。
    """
    async for event in stream:
        if event.get("event") != "on_chat_model_stream":
            yield event
            continue
        chunk = (event.get("data") or {}).get("chunk")
        if chunk is None:
            yield event
            continue
        if not _message_text(chunk) or not _has_reasoning(chunk):
            yield event
            continue
        yield _replace_chunk(event, _drop_message_text(chunk))
        yield _replace_chunk(event, _drop_reasoning_text(chunk))


def install_reasoning_text_split(graph: Any) -> Any:
    """为编译图安装推理与正文分片拆分包装。

    Args:
        graph: 原始 LangGraph 编译图。

    Returns:
        同一个图对象；重复调用不会重复包装。
    """
    if graph is None or not hasattr(graph, "astream_events"):
        return graph
    original = graph.astream_events
    if getattr(original, _WRAPPER_MARK, False):
        return graph

    @functools.wraps(original)
    def astream_events(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        return split_reasoning_text_events(original(*args, **kwargs))

    setattr(astream_events, _WRAPPER_MARK, True)
    graph.astream_events = astream_events
    return graph
