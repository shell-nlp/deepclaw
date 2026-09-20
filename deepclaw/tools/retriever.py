from langchain.tools import tool

from deepclaw.common import create_graph_rag
from deepclaw.common.vector_store import (
    AbstractVectorStore,
    create_default_vector_store,
)
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.settings import settings
from deepclaw.utils import get_embedding_model

DEFAULT_INDEX_NAME = "236"

embeddings = None
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
    global default_retriever, embeddings
    if default_retriever is None:
        embeddings = get_embedding_model()
        default_retriever = create_default_vector_store(
            embedding_model=embeddings,
        )
    return default_retriever


@tool
def retrieve_context(query: str):
    """检索与查询相关的信息。"""
    docs = get_default_retriever().retrieve(
        query=query, k=3, index_names=[DEFAULT_INDEX_NAME]
    )
    context = ""
    for idx, doc in enumerate(docs, start=1):
        context += f"文档 {idx}: \n{doc.get('content', '')}\n\n"
    return context


retrieve_tool = retrieve_context


@tool
def retrieve_graph_context(query: str, graph_name: str = DEFAULT_INDEX_NAME):
    """使用 ES 向量图 RAG 检索与查询相关的上下文。"""
    # 图检索依赖 graph_name 构造实例，因此按调用动态创建。
    es = ElasticsearchVectorStore(
        url=settings.ES_URL,
        username=settings.ES_URSR,
        password=settings.ES_PWD,
        embedding_model=get_default_retriever().embedding_model,
    )
    rag = create_graph_rag(es, graph_name)
    result = rag.retrieve(query=query, k=5)
    passages = result["passages"] if isinstance(result, dict) else result

    context = ""
    for idx, doc in enumerate(passages, start=1):
        context += f"文档 {idx}: \n{doc.get('content', '')}\n\n"
    return context


if __name__ == "__main__":
    query = "等节水灌溉方式。\n水资源短缺地区应当严格控制人造河湖等景观用水"

    r = retrieve_context.invoke(query)
    print(r)

