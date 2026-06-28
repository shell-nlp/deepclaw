from typing import Any

from deepclaw.common.graph_db import (
    GraphDatabaseBase,
    Neo4jGraph,
    NetworkXGraph,
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


__all__ = [
    "AbstractVectorStore",
    "BaseGraphRAG",
    "ElasticGraphRAG",
    "PgGraphRAG",
    "ElasticsearchVectorStore",
    "GraphDatabaseBase",
    "Neo4jGraph",
    "NetworkXGraph",
    "PgVectorStore",
    "VectorStoreBackend",
    "create_default_vector_store",
    "create_graph_rag",
    "create_vector_store",
]

