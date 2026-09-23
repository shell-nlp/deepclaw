from langchain_core.messages.ai import AIMessageChunk

from deepclaw.utils.model_factory import ReasoningChatOpenAI


def _convert(model: ReasoningChatOpenAI, chunk: dict) -> AIMessageChunk:
    """将原始 OpenAI 兼容 chunk 转为 AIMessageChunk。

    Args:
        model: 待测试的聊天模型。
        chunk: 原始 OpenAI 兼容流式 chunk。

    Returns:
        转换后的模型消息分片。
    """
    generation_chunk = model._convert_chunk_to_generation_chunk(
        chunk,
        AIMessageChunk,
    )
    assert generation_chunk is not None
    return generation_chunk.message


def test_reasoning_chat_openai_preserves_native_reasoning_content() -> None:
    """验证兼容网关原生 reasoning_content 会被保留。"""
    model = ReasoningChatOpenAI(
        model="gpt-5.5",
        base_url="https://api.openai.com/v1",
        api_key="test",
    )
    message = _convert(
        model,
        {
            "id": "chatcmpl-native",
            "choices": [
                {
                    "delta": {"reasoning_content": "先分析问题"},
                    "finish_reason": None,
                }
            ],
        },
    )

    assert message.content == ""
    assert message.additional_kwargs["reasoning_content"] == "先分析问题"
