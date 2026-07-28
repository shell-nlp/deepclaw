from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from deepclaw.common.graph_db.base import GraphDatabaseBase


class Neo4jGraph(GraphDatabaseBase):
    """Neo4j 图数据库实现。"""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        """初始化 Neo4j 连接。

        Args:
            uri: Neo4j 数据库 URI（如 bolt://localhost:7687）。
            user: 用户名。
            password: 密码。
            database: 数据库名称，默认为 neo4j。
        """
        from neo4j import GraphDatabase

        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._verify_connection()
        logger.info("已连接到 Neo4j 数据库: {}", self.uri)

    def _verify_connection(self) -> None:
        """验证数据库连接是否正常。"""
        with self.driver.session(database=self.database) as session:
            session.run("RETURN 1")

    def add_node(self, label: str, properties: dict[str, Any] | None = None, node_id: str | None = None) -> str:
        """添加节点，已存在相同 id 的节点时合并属性。

        注意: Neo4j Browser 默认使用节点的 name 或 title 属性作为可视化显示标题，
              因此建议 properties 中包含 "name" 字段（值为中文名称）。

        Args:
            label: 节点标签（即实体类型）。
            properties: 节点属性。
            node_id: 节点唯一标识符（可选，不传时自动生成）。

        Returns:
            节点 ID。
        """
        if properties is None:
            properties = {}
        if node_id:
            properties["id"] = node_id

        resolved_id = node_id or self._generate_node_id(label)
        parameters = {
            "node_id": resolved_id,
            "properties": properties,
            "label": label,
        }

        query = (
            f"MERGE (n:{label} {{id: $node_id}})\n"
            "SET n += $properties\n"
            "RETURN id(n) AS node_internal_id, n.id AS node_id"
        )

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                record = result.single()
                logger.info("成功添加节点: {} - {}", label, record["node_id"])
                return record["node_id"]
        except Exception as e:
            logger.error("添加节点失败: {}", e)
            raise

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relationship_type: str = "LINK",
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """添加边（关系），已存在时合并属性。

        Args:
            from_node_id: 起始节点 ID。
            to_node_id: 目标节点 ID。
            relationship_type: 关系类型。
            properties: 关系属性。

        Returns:
            是否成功添加。
        """
        if properties is None:
            properties = {}

        query = (
            "MATCH (a {id: $from_node_id}), (b {id: $to_node_id})\n"
            f"MERGE (a)-[r:{relationship_type}]->(b)\n"
            "SET r += $properties\n"
            "RETURN count(r) > 0 AS created"
        )

        parameters = {
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "properties": properties,
        }

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                record = result.single()
                success = record["created"]
                if success:
                    logger.info("成功添加关系: {} -[{}]-> {}", from_node_id, relationship_type, to_node_id)
                else:
                    logger.warning("添加关系失败: 节点未找到")
                return success
        except Exception as e:
            logger.error("添加关系失败: {}", e)
            raise

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """根据节点 ID 获取节点信息。

        Args:
            node_id: 节点 ID。

        Returns:
            节点信息字典（含 id、labels、properties）或 None。
        """
        query = "MATCH (n {id: $node_id}) RETURN n"
        parameters = {"node_id": node_id}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                record = result.single()
                if record:
                    node = record["n"]
                    return {
                        "id": node.get("id"),
                        "labels": list(node.labels),
                        "properties": dict(node),
                    }
                return None
        except Exception as e:
            logger.error("查询节点失败: {}", e)
            raise

    def get_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        """根据标签获取所有节点。

        Args:
            label: 节点标签。

        Returns:
            节点列表，每项含 id、labels、properties。
        """
        query = f"MATCH (n:{label}) RETURN n"

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query)
                nodes = []
                for record in result:
                    node = record["n"]
                    nodes.append({
                        "id": node.get("id"),
                        "labels": list(node.labels),
                        "properties": dict(node),
                    })
                return nodes
        except Exception as e:
            logger.error("查询节点失败: {}", e)
            raise

    def get_neighbors(self, node_id: str, relationship_type: str | None = None) -> list[dict[str, Any]]:
        """获取节点的邻居节点。

        Args:
            node_id: 节点 ID。
            relationship_type: 关系类型（可选，不传时返回所有关系类型的邻居）。

        Returns:
            邻居节点列表，每项含 node（含 id、labels、properties）和 relationship_type。
        """
        if relationship_type:
            query = (
                "MATCH (n {id: $node_id})-[r:" + relationship_type + "]->(neighbor)\n"
                "RETURN neighbor, type(r) AS relationship_type"
            )
        else:
            query = "MATCH (n {id: $node_id})-[r]->(neighbor)\nRETURN neighbor, type(r) AS relationship_type"

        parameters = {"node_id": node_id}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                neighbors = []
                for record in result:
                    neighbor = record["neighbor"]
                    neighbors.append({
                        "node": {
                            "id": neighbor.get("id"),
                            "labels": list(neighbor.labels),
                            "properties": dict(neighbor),
                        },
                        "relationship_type": record["relationship_type"],
                    })
                return neighbors
        except Exception as e:
            logger.error("查询邻居节点失败: {}", e)
            raise

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有关系。

        Args:
            node_id: 节点 ID。

        Returns:
            是否成功删除。
        """
        query = "MATCH (n {id: $node_id})\nDETACH DELETE n\nRETURN count(n) > 0 AS deleted"
        parameters = {"node_id": node_id}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                record = result.single()
                deleted = record["deleted"]
                if deleted:
                    logger.info("成功删除节点: {}", node_id)
                else:
                    logger.warning("删除节点失败: 节点不存在")
                return deleted
        except Exception as e:
            logger.error("删除节点失败: {}", e)
            raise

    def delete_edge(self, from_node_id: str, to_node_id: str, relationship_type: str) -> bool:
        """删除指定的关系。

        Args:
            from_node_id: 起始节点 ID。
            to_node_id: 目标节点 ID。
            relationship_type: 关系类型。

        Returns:
            是否成功删除。
        """
        query = (
            "MATCH (a {id: $from_node_id})-[r:" + relationship_type + "]->(b {id: $to_node_id})\n"
            "DELETE r\n"
            "RETURN count(r) > 0 AS deleted"
        )

        parameters = {"from_node_id": from_node_id, "to_node_id": to_node_id}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                record = result.single()
                deleted = record["deleted"]
                if deleted:
                    logger.info("成功删除关系: {} -[{}]-> {}", from_node_id, relationship_type, to_node_id)
                else:
                    logger.warning("删除关系失败: 关系不存在")
                return deleted
        except Exception as e:
            logger.error("删除关系失败: {}", e)
            raise

    def export_data(self) -> dict[str, list[dict[str, Any]]]:
        """导出 Neo4j 图谱为可移植数据。

        Returns:
            包含 nodes 和 edges 的图谱数据。
        """
        nodes = self.run_cypher_query("MATCH (n) RETURN n.id AS id, labels(n) AS labels, properties(n) AS properties")
        edges = self.run_cypher_query(
            "MATCH (source)-[relationship]->(target) "
            "RETURN source.id AS from_node_id, target.id AS to_node_id, "
            "type(relationship) AS relationship_type, properties(relationship) AS properties"
        )
        return {"nodes": nodes, "edges": edges}

    def export_to_neo4j_csv(self, directory: str | Path) -> tuple[Path, Path]:
        """流式导出可由 neo4j-admin database import 批量导入的 CSV 文件。

        Args:
            directory: 输出目录。

        Returns:
            节点 CSV 和关系 CSV 的路径。
        """
        output_directory = Path(directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        node_path = output_directory / "nodes.csv"
        relationship_path = output_directory / "relationships.csv"
        node_summary = self._export_nodes_csv(node_path)
        relationship_summary = self._export_relationships_csv(relationship_path)
        self._log_graph_summary(
            "Neo4j CSV 导出",
            {
                "node_count": node_summary["node_count"],
                "relationship_count": relationship_summary["relationship_count"],
                "node_labels": node_summary["node_labels"],
                "relationship_types": relationship_summary["relationship_types"],
            },
        )
        return node_path, relationship_path

    def import_from_neo4j_csv(
        self,
        nodes_path: str | Path,
        relationships_path: str | Path,
        clear_existing: bool = False,
        batch_size: int = 1000,
    ) -> None:
        """分批导入 Neo4j 批量导入 CSV 格式的数据。

        Args:
            nodes_path: 节点 CSV 文件路径。
            relationships_path: 关系 CSV 文件路径。
            clear_existing: 是否先清空当前图谱。
            batch_size: 每次 UNWIND 写入的记录数。
        """
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        nodes = self._read_nodes_csv(Path(nodes_path))
        edges = self._read_relationships_csv(Path(relationships_path))
        if clear_existing:
            self.clear_database()
        self._import_nodes_in_batches(nodes, batch_size)
        self._import_edges_in_batches(edges, batch_size)
        self._log_graph_summary("Neo4j CSV 导入", self._build_graph_summary(nodes, edges))

    def _import_nodes_in_batches(self, nodes: list[dict[str, Any]], batch_size: int) -> None:
        """按标签组合分批写入节点。

        Args:
            nodes: 节点数据列表。
            batch_size: 每批记录数。
        """
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for node in nodes:
            groups.setdefault(tuple(node["labels"]), []).append(node)
        with self.driver.session(database=self.database) as session:
            for labels, group in groups.items():
                escaped_labels = ":".join(f"`{label.replace('`', '``')}`" for label in labels)
                query = (
                    f"UNWIND $rows AS row\nMERGE (node:{escaped_labels} {{id: row.id}})\n"
                    "SET node += row.properties\nSET node.id = row.id"
                )
                for start in range(0, len(group), batch_size):
                    session.run(query, {"rows": group[start : start + batch_size]}).consume()

    def _import_edges_in_batches(self, edges: list[dict[str, Any]], batch_size: int) -> None:
        """按关系类型分批写入关系。

        Args:
            edges: 关系数据列表。
            batch_size: 每批记录数。
        """
        groups: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            groups.setdefault(edge["relationship_type"], []).append(edge)
        with self.driver.session(database=self.database) as session:
            for relationship_type, group in groups.items():
                escaped_type = relationship_type.replace("`", "``")
                query = (
                    "UNWIND $rows AS row\n"
                    "MATCH (source {id: row.from_node_id}), (target {id: row.to_node_id})\n"
                    f"MERGE (source)-[relationship:`{escaped_type}`]->(target)\n"
                    "SET relationship += row.properties"
                )
                for start in range(0, len(group), batch_size):
                    session.run(query, {"rows": group[start : start + batch_size]}).consume()

    def _export_nodes_csv(self, path: Path) -> dict[str, Any]:
        """流式写入 Neo4j 节点 CSV 文件。

        Args:
            path: 节点 CSV 文件路径。
        """
        property_types = self._get_property_types("MATCH (n) UNWIND keys(n) AS key RETURN key, n[key] AS value")
        node_count = 0
        label_counts: dict[str, int] = {}
        headers = ["node_id:ID", ":LABEL", *self._property_headers(property_types)]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    "MATCH (n) RETURN n.id AS node_id, labels(n) AS labels, properties(n) AS properties"
                )
                for record in result:
                    node_count += 1
                    for label in record["labels"]:
                        label_counts[label] = label_counts.get(label, 0) + 1
                    row = {
                        "node_id:ID": record["node_id"],
                        ":LABEL": ";".join(record["labels"]),
                    }
                    row.update(self._property_row(dict(record["properties"]), property_types))
                    writer.writerow(row)
        return {"node_count": node_count, "node_labels": label_counts}

    def _export_relationships_csv(self, path: Path) -> dict[str, Any]:
        """流式写入 Neo4j 关系 CSV 文件。

        Args:
            path: 关系 CSV 文件路径。
        """
        property_types = self._get_property_types("MATCH ()-[r]->() UNWIND keys(r) AS key RETURN key, r[key] AS value")
        relationship_count = 0
        relationship_types: dict[str, int] = {}
        headers = [":START_ID", ":END_ID", ":TYPE", *self._property_headers(property_types)]
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            with self.driver.session(database=self.database) as session:
                result = session.run(
                    "MATCH (source)-[relationship]->(target) "
                    "RETURN source.id AS from_node_id, target.id AS to_node_id, "
                    "type(relationship) AS relationship_type, properties(relationship) AS properties"
                )
                for record in result:
                    relationship_count += 1
                    relationship_type = record["relationship_type"]
                    relationship_types[relationship_type] = relationship_types.get(relationship_type, 0) + 1
                    row = {
                        ":START_ID": record["from_node_id"],
                        ":END_ID": record["to_node_id"],
                        ":TYPE": record["relationship_type"],
                    }
                    row.update(self._property_row(dict(record["properties"]), property_types))
                    writer.writerow(row)
        return {
            "relationship_count": relationship_count,
            "relationship_types": relationship_types,
        }

    def _get_property_types(self, query: str) -> dict[str, str]:
        """扫描属性值并推断 Neo4j CSV 列类型。

        Args:
            query: 返回 key 和 value 字段的 Cypher 查询。

        Returns:
            属性名到 Neo4j CSV 类型的映射。
        """
        property_types: dict[str, str] = {}
        with self.driver.session(database=self.database) as session:
            for record in session.run(query):
                key = record["key"]
                value_type = self._neo4j_csv_type(record["value"])
                current_type = property_types.get(key)
                if current_type is None:
                    property_types[key] = value_type
                elif current_type != value_type:
                    property_types[key] = "string"
        return property_types

    def import_data(self, data: dict[str, list[dict[str, Any]]], clear_existing: bool = False) -> None:
        """导入可移植图谱数据。

        Args:
            data: 包含 nodes 和 edges 的图谱数据。
            clear_existing: 是否先清空当前图谱。
        """
        nodes, edges = GraphDatabaseBase._validate_graph_data(data)
        if clear_existing:
            self.clear_database()
        for node in nodes:
            self._add_node_with_labels(node["id"], node["labels"], dict(node["properties"]))
        for edge in edges:
            if not self.add_edge(
                edge["from_node_id"],
                edge["to_node_id"],
                edge["relationship_type"],
                dict(edge["properties"]),
            ):
                raise ValueError("关系引用了不存在的节点")

    def _add_node_with_labels(self, node_id: str, labels: list[str], properties: dict[str, Any]) -> None:
        """创建或更新具有多个标签的节点。

        Args:
            node_id: 节点唯一标识符。
            labels: 节点标签列表。
            properties: 节点属性。
        """
        escaped_labels = ":".join(f"`{label.replace('`', '``')}`" for label in labels)
        query = f"MERGE (n:{escaped_labels} {{id: $node_id}})\nSET n += $properties\nSET n.id = $node_id"
        with self.driver.session(database=self.database) as session:
            session.run(query, {"node_id": node_id, "properties": properties})

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.driver:
            self.driver.close()
            logger.info("已关闭 Neo4j 连接")

    def run_cypher_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """执行自定义 Cypher 查询。

        Args:
            query: Cypher 查询语句。
            parameters: 查询参数。

        Returns:
            查询结果列表。
        """
        if parameters is None:
            parameters = {}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error("Cypher 查询失败: {}", e)
            raise

    def clear_database(self) -> None:
        """清空数据库（谨慎使用）。"""
        query = "MATCH (n) DETACH DELETE n"
        try:
            with self.driver.session(database=self.database) as session:
                session.run(query)
            logger.info("数据库已清空")
        except Exception as e:
            logger.error("清空数据库失败: {}", e)
            raise

    def _generate_node_id(self, label: str) -> str:
        """生成新节点 ID。

        Args:
            label: 节点标签。

        Returns:
            格式为 {label}_{uuid 前 8 位} 的 ID。
        """
        return f"{label}_{uuid4().hex[:8]}"
