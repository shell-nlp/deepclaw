"""提供基于 LangGraph interrupt 的人机协作工具。"""

from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt
from pydantic import BaseModel, Field


class AskUserOption(BaseModel):
    """单个提问选项。

    Args:
        label: 选项显示文案，不能为空。
        description: 可选的选项说明文字，帮助用户理解该选项含义。
    """

    label: str = Field(..., max_length=100)
    description: str = Field(default="", max_length=200)


@tool
def ask_user(
    question: str,
    header: str | None = None,
    options: list[AskUserOption] | None = None,
    multiple: bool = False,
    custom: bool = True,
) -> Any:
    """暂停 Agent 并向用户提问，在图恢复后返回用户回答。

    Args:
        question: 展示给用户的问题，不能为空。
        header: 可选的短标签，用于客户端问题标题，最多 30 字符。
        options: 可选的建议选项列表，由客户端决定是否渲染为选项控件。
        multiple: 是否允许用户选择多个选项，默认单选。
        custom: 是否允许用户输入自定义回答，默认允许。

    Returns:
        用户通过 LangGraph Command(resume=...) 提供的回答。
    """
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question 不能为空")

    if header is not None and len(header) > 30:
        raise ValueError("header 不能超过 30 字符")

    normalized_options = None
    if options is not None:
        normalized_options = []
        for option in options:
            label = option.label.strip()
            if not label:
                raise ValueError("options 不能包含空选项")
            built_option: dict[str, Any] = {"label": label}
            description = option.description.strip()
            if description:
                built_option["description"] = description
            normalized_options.append(built_option)

    payload: dict[str, Any] = {"question": normalized_question}
    if header and header.strip():
        payload["header"] = header.strip()
    if normalized_options:
        payload["options"] = normalized_options
    if multiple:
        payload["multiple"] = True
    payload["custom"] = custom

    return interrupt(payload)
