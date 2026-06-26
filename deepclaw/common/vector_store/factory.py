from __future__ import annotations

from typing import Literal

from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.settings import settings

VectorStoreBackend = Literal["elasticsearch", "pgsql"]


def _load_pg_vector_store():
    from deepclaw.common.vector_store.pgsql import PgVectorStore

    return PgVectorStore


def create_vector_store(
    *,
    backend: VectorStoreBackend,
    embedding_model=None,
    embedding_dimensions: int | None = None,
) -> AbstractVectorStore:
    """统一创建向量库实例，减少业务侧直接依赖具体实现。"""
    if backend == "elasticsearch":
        if not settings.ES_URL:
            raise ValueError("未配置 ES_URL，无法创建 ElasticsearchVectorStore")
        return ElasticsearchVectorStore(
            url=settings.ES_URL,
            username=settings.ES_URSR,
            password=settings.ES_PWD,
            embedding_model=embedding_model,
        )

    if not settings.PG_DATABASE_URL:
        raise ValueError("未配置 PG_DATABASE_URL，无法创建 PgVectorStore")
    pg_vector_store_cls = _load_pg_vector_store()

    return pg_vector_store_cls(
        database_url=settings.PG_DATABASE_URL,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )

def create_default_vector_store(
    *,
    embedding_model=None,
    embedding_dimensions: int | None = None,
) -> AbstractVectorStore:
    """按配置创建默认向量库实例，减少业务侧显式判断后端。"""
    return create_vector_store(
        backend=settings.VECTOR_STORE_BACKEND,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
