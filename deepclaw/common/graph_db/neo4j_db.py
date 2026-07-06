from __future__ import annotations

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

    def add_node(
        self, label: str, properties: dict[str, Any] | None = None, node_id: str | None = None
    ) -> str:
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

    def get_neighbors(
        self, node_id: str, relationship_type: str | None = None
    ) -> list[dict[str, Any]]:
        """获取节点的邻居节点。

        Args:
            node_id: 节点 ID。
            relationship_type: 关系类型（可选，不传时返回所有关系类型的邻居）。

        Returns:
            邻居节点列表，每项含 node（含 id、labels、properties）和 relationship_type。
        """
        if relationship_type:
            query = (
                "MATCH (n {id: $node_id})-[r:"
                + relationship_type
                + "]->(neighbor)\n"
                "RETURN neighbor, type(r) AS relationship_type"
            )
        else:
            query = (
                "MATCH (n {id: $node_id})-[r]->(neighbor)\n"
                "RETURN neighbor, type(r) AS relationship_type"
            )

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
        query = (
            "MATCH (n {id: $node_id})\n"
            "DETACH DELETE n\n"
            "RETURN count(n) > 0 AS deleted"
        )
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
        query = (
            "MATCH (a {id: $from_node_id})-[r:"
            + relationship_type
            + "]->(b {id: $to_node_id})\n"
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

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.driver:
            self.driver.close()
            logger.info("已关闭 Neo4j 连接")

    def run_cypher_query(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
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
