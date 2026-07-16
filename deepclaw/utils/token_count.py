"""Token 计数相关工具。"""

import json
from pathlib import Path
from typing import Any, Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import MessageLikeRepresentation, convert_to_messages
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from deepclaw.settings import settings

TokenCounter = Callable[[str], int]


def _dump_token_payload(value: Any) -> str:
    """返回用于 token 计数的紧凑字符串表示。

    Args:
        value: 需要转换为字符串的任意 Python 对象。
    """

    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except TypeError:
        return repr(value)


def _resolve_hf_tokenizer(hf_tokenizer: Any):
    """解析 Hugging Face tokenizer。

    Args:
        hf_tokenizer: `Tokenizer` 实例、Hugging Face 仓库名，或本地 `tokenizer.json` 路径。
    """

    if hf_tokenizer is None:
        return None

    from tokenizers import Tokenizer

    if hasattr(hf_tokenizer, "encode") and hasattr(hf_tokenizer, "get_vocab_size"):
        return hf_tokenizer

    if not isinstance(hf_tokenizer, str):
        msg = "hf_tokenizer 必须是 tokenizers.Tokenizer 实例、仓库名或本地 tokenizer.json 路径。"
        raise TypeError(msg)

    tokenizer_path = Path(hf_tokenizer)
    if tokenizer_path.exists():
        return Tokenizer.from_file(str(tokenizer_path))
    return Tokenizer.from_pretrained(hf_tokenizer)


def _resolve_token_counter(
    *,
    model_name: str | None,
    encoding_name: str | None,
    hf_tokenizer: Any = None,
) -> TokenCounter:
    """解析可用于精确 token 计数的编码器函数。

    Args:
        model_name: 模型名称，优先用于 `tiktoken.encoding_for_model()`。
        encoding_name: 显式指定的 tiktoken encoding 名称。
        hf_tokenizer: Hugging Face tokenizer 实例、仓库名，或本地 `tokenizer.json` 路径。
    """

    tokenizer = _resolve_hf_tokenizer(hf_tokenizer)
    if tokenizer is not None:
        return lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)

    import tiktoken

    if encoding_name:
        encoding = tiktoken.get_encoding(encoding_name)
        return lambda text: len(encoding.encode(text))

    resolved_model_name = model_name or settings.CHAT_MODEL_NAME
    try:
        encoding = tiktoken.encoding_for_model(resolved_model_name)
    except KeyError:
        fallback_encoding = (
            "o200k_base"
            if resolved_model_name.startswith(("gpt-4o", "gpt-4.1", "o1", "o3"))
            else "cl100k_base"
        )
        encoding = tiktoken.get_encoding(fallback_encoding)
    return lambda text: len(encoding.encode(text))


def _get_message_openai_role(message: BaseMessage) -> str:
    """返回消息在 OpenAI/ChatML 语义下对应的 role。

    Args:
        message: 需要提取 role 的 LangChain 消息对象。
    """

    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, SystemMessage):
        role = message.additional_kwargs.get("__openai_role__", "system")
        if not isinstance(role, str):
            msg = f"期望 '__openai_role__' 为字符串，实际得到 {type(role).__name__}。"
            raise TypeError(msg)
        return role
    if isinstance(message, FunctionMessage):
        return "function"
    if isinstance(message, ChatMessage):
        return message.role
    return message.type


def _count_message_content_tokens(
    content: Any,
    *,
    count_text_tokens: TokenCounter,
    tokens_per_image: int,
) -> int:
    """计算单条消息内容部分的 token 数。

    Args:
        content: 消息内容，支持字符串、多模态块数组或其他可序列化对象。
        count_text_tokens: 单段文本 token 计数函数。
        tokens_per_image: 每个图片块按固定值折算的 token 数。
    """

    if isinstance(content, str):
        return count_text_tokens(content)

    if isinstance(content, list):
        total_tokens = 0
        for block in content:
            if isinstance(block, str):
                total_tokens += count_text_tokens(block)
                continue
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type in {"image", "image_url"}:
                    total_tokens += tokens_per_image
                elif block_type == "text":
                    total_tokens += count_text_tokens(str(block.get("text", "")))
                else:
                    total_tokens += count_text_tokens(_dump_token_payload(block))
                continue
            total_tokens += count_text_tokens(_dump_token_payload(block))
        return total_tokens

    return count_text_tokens(_dump_token_payload(content))


def _convert_ai_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 LangChain tool calls 转为 OpenAI 风格结构。

    Args:
        tool_calls: LangChain `AIMessage.tool_calls` 中的工具调用列表。
    """

    return [
        {
            "type": "function",
            "id": tool_call["id"],
            "function": {
                "name": tool_call["name"],
                "arguments": json.dumps(tool_call["args"], ensure_ascii=False, separators=(",", ":")),
            },
        }
        for tool_call in tool_calls
    ]


def count_text_tokens(
    text: str,
    *,
    model_name: str | None = None,
    encoding_name: str | None = None,
    hf_tokenizer: Any = None,
) -> int:
    """使用模型对应 tokenizer 精确计算文本 token 数。

    Args:
        text: 需要计算 token 数的文本内容。
        model_name: 模型名称，未传时默认使用 `settings.CHAT_MODEL_NAME`。
        encoding_name: 显式指定的 tiktoken encoding 名称。
        hf_tokenizer: Hugging Face tokenizer 实例、仓库名，或本地 `tokenizer.json` 路径。
    """

    counter = _resolve_token_counter(
        model_name=model_name,
        encoding_name=encoding_name,
        hf_tokenizer=hf_tokenizer,
    )
    return counter(text)


def count_message_tokens(
    messages: list[MessageLikeRepresentation] | tuple[MessageLikeRepresentation, ...],
    *,
    model_name: str | None = None,
    encoding_name: str | None = None,
    hf_tokenizer: Any = None,
    tools: list[BaseTool | dict[str, Any]] | None = None,
    count_name: bool = True,
    tokens_per_message: int = 3,
    tokens_per_name: int = 1,
    tokens_per_image: int = 85,
    reply_primer_tokens: int = 3,
) -> int:
    """使用模型 tokenizer 计算消息列表的 token 数。

    Args:
        messages: LangChain 消息列表，支持字符串、字典和 `BaseMessage`。
        model_name: 模型名称，未传时默认使用 `settings.CHAT_MODEL_NAME`。
        encoding_name: 显式指定的 tiktoken encoding 名称。
        hf_tokenizer: Hugging Face tokenizer 实例、仓库名，或本地 `tokenizer.json` 路径。
        tools: 需要一并计入 token 的工具 schema 列表。
        count_name: 是否把消息 `name` 字段计入 token 数。
        tokens_per_message: 每条消息的固定协议开销。
        tokens_per_name: 存在 `name` 字段时的额外协议开销。
        tokens_per_image: 每个图片块按固定值折算的 token 数。
        reply_primer_tokens: assistant 回复前缀的固定协议开销。
    """

    counter = _resolve_token_counter(
        model_name=model_name,
        encoding_name=encoding_name,
        hf_tokenizer=hf_tokenizer,
    )
    converted_messages = convert_to_messages(messages)
    total_tokens = reply_primer_tokens

    if tools:
        for tool in tools:
            tool_payload = tool if isinstance(tool, dict) else convert_to_openai_tool(tool)
            total_tokens += counter(_dump_token_payload(tool_payload))

    for message in converted_messages:
        total_tokens += tokens_per_message
        total_tokens += counter(_get_message_openai_role(message))
        total_tokens += _count_message_content_tokens(
            message.content,
            count_text_tokens=counter,
            tokens_per_image=tokens_per_image,
        )

        if count_name and message.name:
            total_tokens += counter(message.name)
            total_tokens += tokens_per_name

        if isinstance(message, AIMessage) and message.tool_calls:
            total_tokens += counter(_dump_token_payload(_convert_ai_tool_calls(message.tool_calls)))

        if isinstance(message, ToolMessage):
            total_tokens += counter(message.tool_call_id)

    return total_tokens


def _run_demo() -> None:
    """运行 token 计数示例。

    Args:
        无额外参数。
    """

    sample_text = "你好，请帮我总结这段对话，并提炼关键行动项。"
    sample_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "查询指定城市天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                    },
                    "required": ["city"],
                },
            },
        }
    ]
    sample_messages = [
        SystemMessage(content="你是一个严谨的中文助手。"),
        HumanMessage(content="请先总结需求，再给出实施步骤。"),
        AIMessage(
            content="我先调用天气工具确认外部信息。",
            tool_calls=[
                {
                    "id": "call_demo_weather",
                    "name": "get_weather",
                    "args": {"city": "上海"},
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content='{"city":"上海","weather":"晴","temperature":30}',
            tool_call_id="call_demo_weather",
        ),
        AIMessage(content="工具结果已收到，接下来我会结合天气信息继续回答。"),
    ]

    print("== Token Count Demo ==")
    print(f"text: {sample_text}")
    print(f"text_tokens: {count_text_tokens(sample_text)}")
    print(f"message_count: {len(sample_messages)}")
    print(f"message_tokens_without_tools: {count_message_tokens(sample_messages)}")
    print(f"message_tokens_with_tools: {count_message_tokens(sample_messages, tools=sample_tools)}")


if __name__ == "__main__":
    _run_demo()
