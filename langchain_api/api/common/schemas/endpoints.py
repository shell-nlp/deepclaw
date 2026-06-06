import uuid
from typing import Literal, Union

from pydantic import BaseModel, Field


class TextContentBlock(BaseModel):
    """文本内容块"""

    type: Literal["text"] = "text"
    text: str


class ImageContentBlock(BaseModel):
    """图片内容块，支持 URL 或 base64 编码"""

    type: Literal["image"] = "image"
    url: str | None = None
    base64: str | None = None
    mime_type: str | None = None


ContentBlock = Union[TextContentBlock, ImageContentBlock]
MessageContent = Union[str, list[ContentBlock]]


class GeneralAPIRequest(BaseModel):
    query: MessageContent | None = Field(
        None,
        description="用户输入的查询，支持字符串或结构化多模态内容（文本、图片等）",
        examples=[
            "请你执行如下任务：\n1. 计算 10 + 10 的结果。\n2. 将结果乘以 5。",
            [
                {"type": "text", "text": "这张照片里是什么动物？"},
                {
                    "type": "image",
                    "url": "https://example.com/image.jpg",
                    "mime_type": "image/jpeg",
                },
            ],
        ],
    )
    resume: dict | None = Field(
        None,
        description="恢复信息",
        examples=[
            {"decisions": [{"type": "approve"}]},
            {
                "decisions": [
                    {
                        "type": "reject",
                        "message": "不，这个操作不符合预期，请调整后继续。",
                    }
                ]
            },
            {
                "decisions": [
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": "new_tool_name",
                            "args": {"key1": "new_value", "key2": "original_value"},
                        },
                    }
                ]
            },
        ],
    )
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="会话 ID"
    )
    stream: bool = Field(default=True, description="是否流式响应 token")


class StreamResponse(BaseModel):
    event: Literal["token", "tool_calls", "tool_output", "__interrupt__"] = "token"
    data: dict | None = None
