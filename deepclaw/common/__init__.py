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
from deepclaw.common.object_storage import (
    LocalObjectStorage,
    ObjectStorage,
    ObjectStoragePDFReader,
    create_object_storage,
)
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
    "DOCLING_SUPPORTED_SUFFIXES",
    "DoclingDocumentParser",
    "ElasticsearchVectorStore",
    "GraphDatabaseBase",
    "Neo4jGraph",
    "NetworkXGraph",
    "LocalObjectStorage",
    "ObjectStorage",
    "ObjectStoragePDFReader",
    "PgVectorStore",
    "create_object_storage",
    "VectorStoreBackend",
    "create_default_vector_store",
    "create_document_parser",
    "create_vector_store",
    "is_docling_available",
]

