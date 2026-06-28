from __future__ import annotations

from typing import Any
from uuid import uuid4

import networkx as nx

from deepclaw.common.graph_db.base import GraphDatabaseBase


class NetworkXGraph(GraphDatabaseBase):
    """NetworkX 内存图数据库实现。

    使用 networkx.MultiDiGraph 作为底层存储，支持多类型边和属性。
    适用于测试、小规模数据或无需持久化的场景。
    """

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._node_labels: dict[str, str] = {}

    def add_node(
        self, label: str, properties: dict[str, Any] | None = None, node_id: str | None = None
    ) -> str:
        if properties is None:
            properties = {}
        resolved_id = node_id or self._generate_node_id(label)

        attrs = dict(properties)
        attrs["_label"] = label
        attrs["_id"] = resolved_id
        self._graph.add_node(resolved_id, **attrs)
        self._node_labels[resolved_id] = label
        return resolved_id

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relationship_type: str = "LINK",
        properties: dict[str, Any] | None = None,
    ) -> bool:
        if from_node_id not in self._graph:
            return False
        if to_node_id not in self._graph:
            return False
        if properties is None:
            properties = {}
        self._graph.add_edge(
            from_node_id, to_node_id, key=relationship_type, **properties
        )
        return True

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if node_id not in self._graph:
            return None
        attrs = dict(self._graph.nodes[node_id])
        label = attrs.pop("_label", None)
        return {
            "id": attrs.pop("_id", node_id),
            "labels": [label] if label else [],
            "properties": attrs,
        }

    def get_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        results = []
        for node_id, attrs in self._graph.nodes(data=True):
            if attrs.get("_label") == label:
                node_attrs = dict(attrs)
                results.append({
                    "id": node_attrs.pop("_id", node_id),
                    "labels": [node_attrs.pop("_label", label)],
                    "properties": node_attrs,
                })
        return results

    def get_neighbors(
        self, node_id: str, relationship_type: str | None = None
    ) -> list[dict[str, Any]]:
        if node_id not in self._graph:
            return []

        neighbors = []
        for _, target, edge_key in self._graph.out_edges(node_id, keys=True):
            if relationship_type is None or edge_key == relationship_type:
                nbr_data = dict(self._graph.nodes[target])
                neighbors.append({
                    "node": {
                        "id": nbr_data.pop("_id", target),
                        "labels": [nbr_data.pop("_label", "")] if "_label" in nbr_data else [],
                        "properties": nbr_data,
                    },
                    "relationship_type": edge_key,
                })

        for source, _, edge_key in self._graph.in_edges(node_id, keys=True):
            if relationship_type is None or edge_key == relationship_type:
                if not any(n["node"]["id"] == source for n in neighbors):
                    nbr_data = dict(self._graph.nodes[source])
                    neighbors.append({
                        "node": {
                            "id": nbr_data.pop("_id", source),
                            "labels": [nbr_data.pop("_label", "")] if "_label" in nbr_data else [],
                            "properties": nbr_data,
                        },
                        "relationship_type": edge_key,
                    })

        return neighbors

    def delete_node(self, node_id: str) -> bool:
        if node_id not in self._graph:
            return False
        self._graph.remove_node(node_id)
        self._node_labels.pop(node_id, None)
        return True

    def delete_edge(
        self, from_node_id: str, to_node_id: str, relationship_type: str
    ) -> bool:
        if not self._graph.has_edge(from_node_id, to_node_id, key=relationship_type):
            return False
        self._graph.remove_edge(from_node_id, to_node_id, key=relationship_type)
        return True

    def close(self) -> None:
        self._graph.clear()
        self._node_labels.clear()

    def clear_database(self) -> None:
        """清空所有节点和边。"""
        self._graph.clear()
        self._node_labels.clear()

    def _generate_node_id(self, label: str) -> str:
        return f"{label}_{uuid4().hex[:8]}"
