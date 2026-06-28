from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GraphDatabaseBase(ABC):
    """图数据库抽象基类，定义统一的图操作接口。

    所有图数据库后端（Neo4j、NetworkX、NebulaGraph 等）需继承此类并实现抽象方法。
    """

    @abstractmethod
    def add_node(
        self, label: str, properties: dict[str, Any] | None = None, node_id: str | None = None
    ) -> str:
        """添加节点。

        Args:
            label: 节点标签（即实体类型）。
            properties: 节点属性。
            node_id: 节点唯一标识符（可选，不传时自动生成）。

        Returns:
            节点 ID。
        """
        ...

    @abstractmethod
    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relationship_type: str = "LINK",
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """添加边（关系）。

        Args:
            from_node_id: 起始节点 ID。
            to_node_id: 目标节点 ID。
            relationship_type: 关系类型。
            properties: 关系属性。

        Returns:
            是否成功添加。
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """根据节点 ID 获取节点信息。

        Args:
            node_id: 节点 ID。

        Returns:
            节点信息字典或 None。
        """
        ...

    @abstractmethod
    def get_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        """根据标签获取所有节点。

        Args:
            label: 节点标签。

        Returns:
            节点列表。
        """
        ...

    @abstractmethod
    def get_neighbors(
        self, node_id: str, relationship_type: str | None = None
    ) -> list[dict[str, Any]]:
        """获取节点的邻居节点。

        Args:
            node_id: 节点 ID。
            relationship_type: 关系类型（可选，不传时返回所有关系类型的邻居）。

        Returns:
            邻居节点列表，每项含 node 和 relationship_type。
        """
        ...

    @abstractmethod
    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有关系。

        Args:
            node_id: 节点 ID。

        Returns:
            是否成功删除。
        """
        ...

    @abstractmethod
    def delete_edge(
        self, from_node_id: str, to_node_id: str, relationship_type: str
    ) -> bool:
        """删除指定的关系。

        Args:
            from_node_id: 起始节点 ID。
            to_node_id: 目标节点 ID。
            relationship_type: 关系类型。

        Returns:
            是否成功删除。
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接，释放资源。"""
        ...
