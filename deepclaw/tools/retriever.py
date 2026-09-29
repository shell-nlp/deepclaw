from collections.abc import Mapping
from typing import Any

from langchain.tools import ToolRuntime, tool

from deepclaw.common.vector_store import (
    AbstractVectorStore,
    create_default_vector_store,
)
from deepclaw.settings import settings
from deepclaw.utils import get_embedding_model

default_retriever: AbstractVectorStore | None = None


def get_default_retriever() -> AbstractVectorStore:
    """按需创建并返回默认向量检索器。

    Args:
        无。

    Returns:
        使用当前向量库配置创建的默认检索器。

    Raises:
        ValueError: 向量库连接地址未配置时抛出。
    """
    global default_retriever
    if default_retriever is None:
        default_retriever = create_default_vector_store(
            embedding_model=get_embedding_model(),
        )
    return default_retriever


def _resolve_index_names(state: Mapping[str, Any] | None) -> list[str]:
    """从图状态中解析参与检索的知识库索引列表。

    Args:
        state: 当前 LangGraph 状态，客户端传入的 index_names 存放在这里。

    Returns:
        去重后的索引名称列表，未配置时返回空列表。
    """
    raw_names = (state or {}).get("index_names")
    if not isinstance(raw_names, list):
        return []
    candidates = [str(item) for item in raw_names if str(item).strip()]
    return list(dict.fromkeys(candidates))


@tool
def retrieve_context(query: str, runtime: ToolRuntime) -> str:
    """检索知识库中与查询相关的内容片段。

    检索范围取自当前请求选中的知识库（state.index_names），未选中任何知识库时不执行检索。
    参数：
        query: 检索用的关键词或问题，建议直接使用用户原话，不要自行改写或翻译。
    返回：
        按相关度排序的知识片段；未选中知识库或未命中时返回提示文本。
    """
    index_names = _resolve_index_names(runtime.state)
    if not index_names:
        return "未选择知识库，本次未执行检索。"
    docs = get_default_retriever().retrieve_with_rrf(
        query=query,
        k=settings.RAG_TOP_K,
        index_names=index_names,
        # 关闭的切片不参与检索；缺少 state 的历史切片仍视为开启。
        filter_conditions={"metadata.state": {"$ne": False}},
    )
    if not docs:
        return "未检索到相关知识库内容。"
    return "\n\n".join(
        f"文档 {index}: \n{doc.get('content', '')}"
        for index, doc in enumerate(docs, start=1)
    )
