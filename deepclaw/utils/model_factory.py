"""模型工厂相关工具。"""

from langchain_deepseek import ChatDeepSeek
from langchain_openai import OpenAIEmbeddings

from deepclaw.settings import settings


def get_chat_model() -> ChatDeepSeek:
    """创建聊天模型实例。

    Args:
        无额外参数。
    """

    return ChatDeepSeek(
        model=settings.CHAT_MODEL_NAME,
        api_base=settings.OPENAI_API_BASE,
        api_key=settings.OPENAI_API_KEY,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "tool_choice": "auto",
            "thinking": {"type": "disabled"},  # enabled  disabled
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
