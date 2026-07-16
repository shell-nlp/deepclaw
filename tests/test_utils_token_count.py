import json

import tiktoken
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from deepclaw.utils import count_message_tokens, count_text_tokens


def _build_test_tokenizer() -> Tokenizer:
    """构造用于测试的最小 Hugging Face tokenizer。

    Args:
        无额外参数。
    """

    tokenizer = Tokenizer(
        WordLevel(
            vocab={
                "[UNK]": 0,
                "user": 1,
                "assistant": 2,
                "tool": 3,
                "你好": 4,
                "world": 5,
                "done": 6,
                "ok": 7,
                "call_1": 8,
            },
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    return tokenizer


def test_count_text_tokens_supports_huggingface_tokenizer_instance() -> None:
    """验证文本 token 计数支持 `tokenizers.Tokenizer` 实例。

    Args:
        无额外参数。
    """

    tokenizer = _build_test_tokenizer()

    assert count_text_tokens("你好 world", hf_tokenizer=tokenizer) == 2


def test_count_message_tokens_supports_huggingface_tokenizer_instance() -> None:
    """验证消息 token 计数支持 `tokenizers.Tokenizer` 实例。

    Args:
        无额外参数。
    """

    tokenizer = _build_test_tokenizer()
    messages = [HumanMessage(content="你好 world")]

    assert count_message_tokens(messages, hf_tokenizer=tokenizer) == 3 + 3 + 1 + 2


def test_count_message_tokens_with_tiktoken_counts_multimodal_and_tools() -> None:
    """验证消息 token 计数会纳入多模态内容、工具调用和工具 schema。

    Args:
        无额外参数。
    """

    encoding = tiktoken.get_encoding("cl100k_base")
    messages = [
        HumanMessage(
            content=[
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                {"type": "metadata", "key": "v"},
            ]
        ),
        AIMessage(
            content="done",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "lookup",
                    "args": {"city": "Shanghai"},
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="ok", tool_call_id="call_1"),
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "查询天气",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    unknown_block = json.dumps({"key": "v", "type": "metadata"}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    tool_call_payload = json.dumps(
        [
            {
                "type": "function",
                "id": "call_1",
                "function": {
                    "name": "lookup",
                    "arguments": json.dumps({"city": "Shanghai"}, ensure_ascii=False, separators=(",", ":")),
                },
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    tool_schema_payload = json.dumps(tools[0], ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    expected = 0
    expected += len(encoding.encode(tool_schema_payload))
    expected += 3
    expected += 3 + len(encoding.encode("user")) + len(encoding.encode("hello")) + 85 + len(encoding.encode(unknown_block))
    expected += 3 + len(encoding.encode("assistant")) + len(encoding.encode("done")) + len(encoding.encode(tool_call_payload))
    expected += 3 + len(encoding.encode("tool")) + len(encoding.encode("ok")) + len(encoding.encode("call_1"))

    assert count_message_tokens(messages, encoding_name="cl100k_base", tools=tools) == expected
