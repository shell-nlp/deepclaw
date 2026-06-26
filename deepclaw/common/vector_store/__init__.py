from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.factory import (
    VectorStoreBackend,
    create_default_vector_store,
    create_vector_store,
)

try:
    from deepclaw.common.vector_store.pgsql import PgVectorStore
except ImportError:  # pragma: no cover - PgSQL 实现落地前允许缺省
    PgVectorStore = None

__all__ = [
    "AbstractVectorStore",
    "ElasticsearchVectorStore",
    "PgVectorStore",
    "VectorStoreBackend",
    "create_default_vector_store",
    "create_vector_store",
]
