from typing import TYPE_CHECKING, Any

from deepclaw.common.graph_db import (
    GraphDatabaseBase,
    Neo4jGraph,
)
from deepclaw.common.docling_parser import (
    DOCLING_SUPPORTED_SUFFIXES,
    DoclingDocumentParser,
    create_document_parser,
    is_docling_available,
)
from deepclaw.common.graph_rag import BaseGraphRAG, ElasticGraphRAG, PgGraphRAG
from deepclaw.common.vector_store import (
    AbstractVectorStore,
    ElasticsearchVectorStore,
    PgVectorStore,
    VectorStoreBackend,
    create_default_vector_store,
    create_vector_store,
)

if TYPE_CHECKING:
    from deepclaw.common.graph_db import NetworkXGraph


def create_graph_rag(
    vector_store: AbstractVectorStore,
    graph_name: str,
    chat_model: Any = None,
) -> BaseGraphRAG:
    """根据向量库类型自动创建对应的 GraphRAG 实例。"""
    if isinstance(vector_store, ElasticsearchVectorStore):
        return ElasticGraphRAG(vector_store, graph_name, chat_model)
    if isinstance(vector_store, PgVectorStore):
        return PgGraphRAG(vector_store, graph_name, chat_model)
    raise ValueError(f"不支持的向量库类型: {type(vector_store).__name__}")


def __getattr__(name: str) -> Any:
    """按需导出可选的 NetworkX 图数据库实现。

    Args:
        name: 请求的模块属性名。
    """
    if name == "NetworkXGraph":
        from deepclaw.common.graph_db import NetworkXGraph

        globals()[name] = NetworkXGraph
        return NetworkXGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AbstractVectorStore",
    "BaseGraphRAG",
    "DOCLING_SUPPORTED_SUFFIXES",
    "DoclingDocumentParser",
    "ElasticGraphRAG",
    "PgGraphRAG",
    "ElasticsearchVectorStore",
    "GraphDatabaseBase",
    "Neo4jGraph",
    "NetworkXGraph",
    "PgVectorStore",
    "VectorStoreBackend",
    "create_default_vector_store",
    "create_document_parser",
    "create_graph_rag",
    "create_vector_store",
    "is_docling_available",
]

