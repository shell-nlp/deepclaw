from langchain_core.messages.ai import AIMessageChunk

from deepclaw.utils.model_factory import DISABLE_THINKING_EXTRA_BODY, ReasoningChatOpenAI, get_chat_model


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


def test_chat_model_uses_configured_upstream_format():
    """验证旧模型沿用兼容协议，Responses 模型使用原生请求体。"""
    config = {"name": "test-model", "api_base": "http://localhost:7869/v1", "api_key": "test"}

    legacy = get_chat_model(catalog_model=config)
    legacy_payload = legacy._get_request_payload("hello")
    assert "messages" in legacy_payload
    assert legacy_payload["extra_body"]["thinking"] == {"type": "disabled"}
    assert "tool_choice" not in legacy_payload
    assert "tool_choice" not in legacy_payload["extra_body"]

    responses = get_chat_model(catalog_model={**config, "upstream_format": "responses"})
    responses_payload = responses._get_request_payload(
        "hello", extra_body={**DISABLE_THINKING_EXTRA_BODY, "response_format": {"type": "json_object"}},
    )
    assert "input" in responses_payload
    assert "messages" not in responses_payload
    assert "extra_body" not in responses_payload
