from typing import TYPE_CHECKING, Any

from deepclaw.common.graph_db.base import GraphDatabaseBase

if TYPE_CHECKING:
    from deepclaw.common.graph_db.networkx import NetworkXGraph

try:
    from deepclaw.common.graph_db.neo4j_db import Neo4jGraph
except ImportError:  # pragma: no cover - neo4j 驱动可选
    Neo4jGraph = None  # type: ignore


def __getattr__(name: str) -> Any:
    """按需加载可选的 NetworkX 图数据库实现。

    Args:
        name: 请求的模块属性名。
    """
    if name == "NetworkXGraph":
        from deepclaw.common.graph_db.networkx import NetworkXGraph

        globals()[name] = NetworkXGraph
        return NetworkXGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "GraphDatabaseBase",
    "Neo4jGraph",
    "NetworkXGraph",
]
