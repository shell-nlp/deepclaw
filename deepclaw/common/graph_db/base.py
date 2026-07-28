from __future__ import annotations

from abc import ABC, abstractmethod
import csv
import json
from pathlib import Path
from typing import Any

from loguru import logger


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
    def export_data(self) -> dict[str, list[dict[str, Any]]]:
        """导出图谱数据。

        Returns:
            包含 nodes 和 edges 的可移植图谱数据。
        """
        ...

    @abstractmethod
    def import_data(
        self, data: dict[str, list[dict[str, Any]]], clear_existing: bool = False
    ) -> None:
        """导入图谱数据。

        Args:
            data: 包含 nodes 和 edges 的图谱数据。
            clear_existing: 是否先清空当前图谱。
        """
        ...

    def export_to_file(self, path: str | Path) -> None:
        """将图谱导出为 JSON 文件。

        Args:
            path: 输出 JSON 文件路径。
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.export_data()
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, default=str)
        self._log_graph_summary("JSON 导出", self._build_graph_summary(data["nodes"], data["edges"]))

    def import_from_file(self, path: str | Path, clear_existing: bool = False) -> None:
        """从 JSON 文件导入图谱。

        Args:
            path: 输入 JSON 文件路径。
            clear_existing: 是否先清空当前图谱。
        """
        with Path(path).open(encoding="utf-8") as file:
            data = json.load(file)
        self.import_data(data, clear_existing=clear_existing)
        self._log_graph_summary("JSON 导入", self._build_graph_summary(data["nodes"], data["edges"]))

    def export_to_neo4j_csv(self, directory: str | Path) -> tuple[Path, Path]:
        """导出可由 neo4j-admin database import 批量导入的 CSV 文件。

        Args:
            directory: 输出目录。

        Returns:
            节点 CSV 和关系 CSV 的路径。
        """
        graph_data = self.export_data()
        nodes = graph_data["nodes"]
        edges = graph_data["edges"]
        output_directory = Path(directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        node_path = output_directory / "nodes.csv"
        relationship_path = output_directory / "relationships.csv"
        self._write_nodes_csv(node_path, nodes)
        self._write_relationships_csv(relationship_path, edges)
        self._log_graph_summary("Neo4j CSV 导出", self._build_graph_summary(nodes, edges))
        return node_path, relationship_path

    def import_from_neo4j_csv(
        self,
        nodes_path: str | Path,
        relationships_path: str | Path,
        clear_existing: bool = False,
    ) -> None:
        """导入由 export_to_neo4j_csv 生成的节点和关系 CSV 文件。

        Args:
            nodes_path: 节点 CSV 文件路径。
            relationships_path: 关系 CSV 文件路径。
            clear_existing: 是否先清空当前图谱。
        """
        nodes = self._read_nodes_csv(Path(nodes_path))
        edges = self._read_relationships_csv(Path(relationships_path))
        self.import_data({"nodes": nodes, "edges": edges}, clear_existing=clear_existing)
        self._log_graph_summary("Neo4j CSV 导入", self._build_graph_summary(nodes, edges))

    @staticmethod
    def _build_graph_summary(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """构建图谱导入导出的摘要统计信息。

        Args:
            nodes: 节点数据列表。
            edges: 关系数据列表。

        Returns:
            节点、关系、标签和关系类型的统计信息。
        """
        label_counts: dict[str, int] = {}
        relationship_type_counts: dict[str, int] = {}
        for node in nodes:
            for label in node["labels"]:
                label_counts[label] = label_counts.get(label, 0) + 1
        for edge in edges:
            relationship_type = edge["relationship_type"]
            relationship_type_counts[relationship_type] = (
                relationship_type_counts.get(relationship_type, 0) + 1
            )
        return {
            "node_count": len(nodes),
            "relationship_count": len(edges),
            "node_labels": label_counts,
            "relationship_types": relationship_type_counts,
        }

    @staticmethod
    def _log_graph_summary(operation: str, summary: dict[str, Any]) -> None:
        """输出图谱导入导出的摘要统计日志。

        Args:
            operation: 已执行的导入或导出操作名称。
            summary: 图谱摘要统计信息。
        """
        logger.info(
            "图谱{}完成: 节点数={}, 关系数={}, 节点标签={}, 关系类型={}",
            operation,
            summary["node_count"],
            summary["relationship_count"],
            summary["node_labels"],
            summary["relationship_types"],
        )

    @classmethod
    def _read_nodes_csv(cls, path: Path) -> list[dict[str, Any]]:
        """读取 Neo4j 节点 CSV 文件。

        Args:
            path: 节点 CSV 文件路径。

        Returns:
            节点数据列表。
        """
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                raise ValueError("节点 CSV 缺少表头")
            id_header = next((header for header in reader.fieldnames if header.endswith(":ID")), None)
            if id_header is None or ":LABEL" not in reader.fieldnames:
                raise ValueError("节点 CSV 缺少 :ID 或 :LABEL 列")
            return [
                {
                    "id": row[id_header],
                    "labels": row[":LABEL"].split(";"),
                    "properties": cls._parse_csv_properties(row, {id_header, ":LABEL"}),
                }
                for row in reader
            ]

    @classmethod
    def _read_relationships_csv(cls, path: Path) -> list[dict[str, Any]]:
        """读取 Neo4j 关系 CSV 文件。

        Args:
            path: 关系 CSV 文件路径。

        Returns:
            关系数据列表。
        """
        required_headers = {":START_ID", ":END_ID", ":TYPE"}
        with path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                raise ValueError("关系 CSV 缺少表头")
            if not required_headers.issubset(reader.fieldnames):
                raise ValueError("关系 CSV 缺少 :START_ID、:END_ID 或 :TYPE 列")
            return [
                {
                    "from_node_id": row[":START_ID"],
                    "to_node_id": row[":END_ID"],
                    "relationship_type": row[":TYPE"],
                    "properties": cls._parse_csv_properties(row, required_headers),
                }
                for row in reader
            ]

    @classmethod
    def _parse_csv_properties(
        cls, row: dict[str, str], metadata_headers: set[str]
    ) -> dict[str, Any]:
        """解析 Neo4j CSV 行中的属性列。

        Args:
            row: CSV 行数据。
            metadata_headers: 不属于属性的表头集合。

        Returns:
            属性字典。
        """
        properties: dict[str, Any] = {}
        for header, value in row.items():
            if header in metadata_headers or value in (None, ""):
                continue
            if ":" not in header:
                raise ValueError(f"属性列缺少类型声明: {header}")
            name, value_type = header.rsplit(":", 1)
            properties[name] = cls._parse_neo4j_csv_value(value, value_type)
        return properties

    @staticmethod
    def _parse_neo4j_csv_value(value: str, value_type: str) -> Any:
        """按 Neo4j CSV 类型声明解析属性值。

        Args:
            value: CSV 单元格内容。
            value_type: Neo4j CSV 类型声明。

        Returns:
            解析后的属性值。
        """
        if value_type.endswith("[]"):
            item_type = value_type[:-2]
            return [
                GraphDatabaseBase._parse_neo4j_csv_value(item, item_type)
                for item in value.split(";")
            ]
        if value_type == "boolean":
            if value.lower() not in {"true", "false"}:
                raise ValueError(f"布尔属性值不合法: {value}")
            return value.lower() == "true"
        if value_type == "long":
            return int(value)
        if value_type == "double":
            return float(value)
        if value_type == "string":
            return value
        raise ValueError(f"不支持的 Neo4j CSV 属性类型: {value_type}")

    @classmethod
    def _write_nodes_csv(cls, path: Path, nodes: list[dict[str, Any]]) -> None:
        """写入 Neo4j 节点 CSV 文件。

        Args:
            path: 节点 CSV 文件路径。
            nodes: 节点数据列表。
        """
        property_types = cls._infer_property_types(nodes)
        headers = ["node_id:ID", ":LABEL", *cls._property_headers(property_types)]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            for node in nodes:
                row = {"node_id:ID": node["id"], ":LABEL": ";".join(node["labels"])}
                row.update(cls._property_row(node["properties"], property_types))
                writer.writerow(row)

    @classmethod
    def _write_relationships_csv(cls, path: Path, edges: list[dict[str, Any]]) -> None:
        """写入 Neo4j 关系 CSV 文件。

        Args:
            path: 关系 CSV 文件路径。
            edges: 关系数据列表。
        """
        property_types = cls._infer_property_types(edges)
        headers = [":START_ID", ":END_ID", ":TYPE", *cls._property_headers(property_types)]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            for edge in edges:
                row = {
                    ":START_ID": edge["from_node_id"],
                    ":END_ID": edge["to_node_id"],
                    ":TYPE": edge["relationship_type"],
                }
                row.update(cls._property_row(edge["properties"], property_types))
                writer.writerow(row)

    @staticmethod
    def _infer_property_types(items: list[dict[str, Any]]) -> dict[str, str]:
        """推断 Neo4j CSV 属性列类型。

        Args:
            items: 包含 properties 字段的数据列表。

        Returns:
            属性名到 Neo4j CSV 类型的映射。
        """
        property_types: dict[str, str] = {}
        for item in items:
            for key, value in item["properties"].items():
                value_type = GraphDatabaseBase._neo4j_csv_type(value)
                current_type = property_types.get(key)
                if current_type is None:
                    property_types[key] = value_type
                elif current_type != value_type:
                    property_types[key] = "string"
        return property_types

    @staticmethod
    def _neo4j_csv_type(value: Any) -> str:
        """获取单个属性值对应的 Neo4j CSV 类型。

        Args:
            value: 属性值。

        Returns:
            Neo4j CSV 类型名称。
        """
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "long"
        if isinstance(value, float):
            return "double"
        if isinstance(value, list) and value:
            item_type = GraphDatabaseBase._neo4j_csv_type(value[0])
            if all(GraphDatabaseBase._neo4j_csv_type(item) == item_type for item in value):
                return f"{item_type}[]"
        return "string"

    @staticmethod
    def _property_headers(property_types: dict[str, str]) -> list[str]:
        """生成 Neo4j CSV 属性表头。

        Args:
            property_types: 属性名到类型的映射。

        Returns:
            属性表头列表。
        """
        return [f"{name}:{value_type}" for name, value_type in sorted(property_types.items())]

    @staticmethod
    def _property_row(properties: dict[str, Any], property_types: dict[str, str]) -> dict[str, str]:
        """将属性转换为 Neo4j CSV 行。

        Args:
            properties: 属性字典。
            property_types: 属性名到类型的映射。

        Returns:
            CSV 表头到单元格内容的映射。
        """
        row: dict[str, str] = {}
        for name, value_type in property_types.items():
            if name not in properties:
                continue
            value = properties[name]
            header = f"{name}:{value_type}"
            if value_type.endswith("[]") and isinstance(value, list):
                row[header] = ";".join(str(item) for item in value)
            elif value_type == "string" and not isinstance(value, str):
                row[header] = json.dumps(value, ensure_ascii=False, default=str)
            else:
                row[header] = str(value).lower() if isinstance(value, bool) else str(value)
        return row

    @staticmethod
    def _validate_graph_data(
        data: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """校验可移植图谱数据格式。

        Args:
            data: 待校验的图谱数据。

        Returns:
            已校验的节点和关系列表。

        Raises:
            ValueError: 图谱数据格式不合法时抛出。
        """
        if not isinstance(data, dict):
            raise ValueError("图谱数据必须是对象")
        nodes = data.get("nodes")
        edges = data.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("图谱数据必须包含 nodes 和 edges 列表")
        for node in nodes:
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("id"), str)
                or not isinstance(node.get("labels"), list)
                or not node["labels"]
                or not all(isinstance(label, str) for label in node["labels"])
                or not isinstance(node.get("properties"), dict)
            ):
                raise ValueError("节点数据格式不合法")
        for edge in edges:
            if (
                not isinstance(edge, dict)
                or not all(
                    isinstance(edge.get(key), str)
                    for key in ("from_node_id", "to_node_id", "relationship_type")
                )
                or not isinstance(edge.get("properties"), dict)
            ):
                raise ValueError("关系数据格式不合法")
        return nodes, edges

    @abstractmethod
    def close(self) -> None:
        """关闭连接，释放资源。"""
        ...
