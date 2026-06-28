import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from elasticsearch import Elasticsearch as ESClient
from loguru import logger

from deepclaw.common.vector_store.base import AbstractVectorStore


class ElasticsearchVectorStore(AbstractVectorStore):
    """基于 Elasticsearch 的向量数据库实现。"""

    def __init__(
        self,
        url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        embedding_model=None,
        refresh_fail_dir: str | Path = ".",
    ):
        """初始化 ElasticsearchVectorStore 实例。

        Args:
            url: Elasticsearch 服务地址
            username: 认证用户名（可选）
            password: 认证密码（可选）
            embedding_model: 嵌入模型实例（可选，未提供时自动获取）
            refresh_fail_dir: 刷新失败记录保存目录，默认为当前目录
        """
        self._url = url
        self._username = username
        self._password = password
        self._embedding_model = embedding_model
        self._refresh_fail_dir = Path(refresh_fail_dir)
        self._es_client: Optional[ESClient] = None

    @property
    def embedding_model(self):
        """获取嵌入模型实例，若未初始化则自动创建。

        Returns:
            嵌入模型实例
        """
        if self._embedding_model is None:
            from deepclaw.utils import get_embedding_model

            self._embedding_model = get_embedding_model()
        return self._embedding_model

    @property
    def es_client(self) -> ESClient:
        """获取 Elasticsearch 客户端实例，若未初始化则自动连接。

        Returns:
            Elasticsearch 客户端实例
        """
        if self._es_client is None:
            self._es_client = ESClient(
                hosts=[self._url],
                basic_auth=(self._username, self._password)
                if self._username and self._password
                else None,
            )
        return self._es_client

    def _resolve_required_indexes(
        self,
        index_names: list[str] | None = None,
        *,
        operation: str = "search",
    ) -> list[str]:
        """解析并验证目标索引列表，确保至少有一个索引名称被提供。

        Args:
            index_names: 目标索引名称列表。
            operation: 操作类型描述，用于错误提示，默认为 "search"。

        Returns:
            解析后的索引名称列表。

        Raises:
            ValueError: 当 index_names 未提供时抛出。
        """
        target_indexes = self.resolve_index_names(index_names)
        if not target_indexes:
            raise ValueError(
                f"index_names is required for {operation} operations"
            )
        return target_indexes

    def vector_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        min_similarity: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """基于向量相似度的语义检索。

        将查询文本转为嵌入向量，在 ES 索引中使用 kNN 搜索相似文档。

        Args:
            query: 查询文本。
            k: 返回的最相似文档数量，默认为 3。
            index_names: 目标索引名称列表。
            min_similarity: 最低相似度阈值，低于此值的文档将被过滤（可选）。
            filter_conditions: 过滤条件字典，支持等值和列表匹配（可选）。

        Returns:
            匹配文档列表，每项包含 id、content、metadata、score 等字段。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="search",
        )
        query_vector = self.embedding_model.embed_query(query)
        knn_query: Dict[str, Any] = {
            "field": "embedding",
            "query_vector": query_vector,
            "num_candidates": max(k * 2, 10),
        }
        if filter_conditions:
            es_filter: List[Dict[str, Any]] = []
            for field, value in filter_conditions.items():
                if isinstance(value, list):
                    es_filter.append({"terms": {field: value}})
                else:
                    es_filter.append({"term": {field: value}})
            knn_query["filter"] = {"bool": {"filter": es_filter}}

        results = self.es_client.search(
            index=target_indexes,
            body={"query": {"knn": knn_query}},
            size=k,
        )
        processed_results = []
        for hit in results["hits"]["hits"]:
            score = hit["_score"]
            if min_similarity is not None and score < min_similarity:
                continue
            processed_results.append(self._hit_to_result(hit))
        return processed_results

    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """基于关键词匹配的全文检索。

        使用 multi_match 在 content、title、summary 字段上进行关键词匹配。

        Args:
            query: 查询关键词文本。
            k: 返回的匹配文档数量，默认为 3。
            index_names: 目标索引名称列表。

        Returns:
            匹配文档列表，每项包含 id、content、metadata、score 等字段。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="search",
        )
        results = self.es_client.search(
            index=target_indexes,
            body={
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content", "title", "summary"],
                        "type": "best_fields",
                        "boost": 0.3,
                    }
                }
            },
            size=k,
        )
        return [self._hit_to_result(hit) for hit in results["hits"]["hits"]]

    def retrieve(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """混合检索，融合向量检索与关键词检索结果。

        分别执行向量检索和关键词检索后，使用 merge_results 方法合并去重，
        得到综合排序的检索结果。

        Args:
            query: 查询文本。
            k: 返回的文档数量，默认为 3。
            index_names: 目标索引名称列表。

        Returns:
            合并后的文档列表，每项包含 id、content、metadata、score 等字段。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="retrieve",
        )
        vector_results = self.vector_search(query, k, index_names=target_indexes)
        keyword_results = self.keyword_search(query, k, index_names=target_indexes)
        merged_results = self.merge_results(
            vector_results=vector_results,
            keyword_results=keyword_results,
            k=k,
        )
        logger.info(
            f"ES检索结果数量：向量检索{len(vector_results)}，关键字检索{len(keyword_results)}，合并后{len(merged_results)}"
        )
        return merged_results

    def vector_graph_retrieve(
        self,
        query: str,
        k: int = 6,
        index_name: Optional[str] = None,
        entity_index_name: Optional[str] = None,
        relation_index_name: Optional[str] = None,
        entity_top_k: int = 5,
        relation_top_k: int = 8,
        expansion_degree: int = 1,
        relation_limit: int = 30,
        min_similarity: Optional[float] = None,
        query_entities: Optional[List[str]] = None,
        return_debug: bool = False,
    ) -> List[Dict[str, Any]] | Dict[str, Any]:
        """
        基于 Elasticsearch 的向量图 RAG 检索。

        借鉴 vector-graph-rag 的思想，但不引入图数据库：
        1. 用查询和查询实体做向量召回，找到种子关系/实体。
        2. 通过 ES 文档中的 metadata.entity_ids / metadata.relation_ids 做邻接扩展。
        3. 关系过多时，再用关系向量相似度做一次裁剪。
        4. 最后用保留下来的 relation_ids / entity_ids 找回原文片段。

        推荐索引结构：
        - passage index: content, embedding, metadata.entity_ids, metadata.relation_ids
        - entity index: content/name, embedding, metadata.relation_ids
        - relation index: content/text, embedding, metadata.entity_ids, metadata.passage_ids

        如果没有独立 entity/relation 索引，也可以只传 index_name，函数会退化为
        普通向量+关键词检索，同时保留相同返回格式。
        """
        if not index_name:
            raise ValueError("index_name is required for vector_graph_retrieve operations")

        entity_index_name = entity_index_name or index_name
        relation_index_name = relation_index_name or index_name
        query_entities = query_entities or self._simple_extract_entities(query)

        seed_entities = self._search_graph_items(
            texts=query_entities,
            index_name=entity_index_name,
            k=entity_top_k,
            min_similarity=min_similarity,
        )
        seed_relations = self._search_graph_items(
            texts=[query],
            index_name=relation_index_name,
            k=relation_top_k,
            min_similarity=min_similarity,
        )

        entity_ids = self._ids_from_hits(seed_entities)
        relation_ids = self._ids_from_hits(seed_relations)

        expanded_entity_ids, expanded_relation_ids, expansion_steps = self._expand_es_graph(
            entity_ids=entity_ids,
            relation_ids=relation_ids,
            entity_index_name=entity_index_name,
            relation_index_name=relation_index_name,
            degree=expansion_degree,
        )

        kept_relations, eviction = self._evict_relations_by_vector(
            query=query,
            relation_ids=expanded_relation_ids,
            relation_index_name=relation_index_name,
            limit=relation_limit,
        )

        passages = self._search_passages_by_graph(
            query=query,
            index_name=index_name,
            relation_ids=kept_relations,
            entity_ids=expanded_entity_ids,
            k=k,
        )

        if not passages:
            passages = self.retrieve(query=query, k=k, index_names=[index_name])

        logger.info(
            "ES向量图RAG: query_entities={}, seed_entities={}, seed_relations={}, expanded_entities={}, expanded_relations={}, passages={}",
            len(query_entities),
            len(entity_ids),
            len(relation_ids),
            len(expanded_entity_ids),
            len(expanded_relation_ids),
            len(passages),
        )

        if not return_debug:
            return passages[:k]

        return {
            "query": query,
            "query_entities": query_entities,
            "passages": passages[:k],
            "seed_entity_ids": entity_ids,
            "seed_relation_ids": relation_ids,
            "expanded_entity_ids": expanded_entity_ids,
            "expanded_relation_ids": expanded_relation_ids,
            "kept_relation_ids": kept_relations,
            "eviction": eviction,
            "expansion_steps": expansion_steps,
        }

    def _search_graph_items(
        self,
        texts: List[str],
        index_name: str,
        k: int,
        min_similarity: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """对多个文本分别执行向量检索，聚合去重后返回结果。

        Args:
            texts: 待检索的文本列表
            index_name: 目标索引名称
            k: 每个文本返回的最多文档数量
            min_similarity: 最低相似度阈值（可选）

        Returns:
            去重后的匹配文档列表
        """
        hits: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        for text in texts:
            if not text.strip():
                continue
            for item in self._vector_search_raw(text, k, index_name, min_similarity):
                item_id = item["id"]
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                hits.append(item)

        return hits

    def _vector_search_raw(
        self,
        query: str,
        k: int,
        index_name: str,
        min_similarity: Optional[float] = None,
        ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """底层向量检索，支持按 ID 列表过滤。

        Args:
            query: 查询文本
            k: 返回的最多文档数量
            index_name: 目标索引名称
            min_similarity: 最低相似度阈值（可选）
            ids: 限定检索的文档 ID 列表（可选）

        Returns:
            匹配文档列表，包含 id、es_id、content、metadata、score 等字段
        """
        query_vector = self.embedding_model.embed_query(query)
        knn_query: Dict[str, Any] = {
            "field": "embedding",
            "query_vector": query_vector,
            "num_candidates": max(k * 5, 20),
        }
        if ids:
            knn_query["filter"] = {
                "bool": {
                    "should": [
                        {"ids": {"values": ids}},
                        {"terms": {"metadata.id": ids}},
                    ],
                    "minimum_should_match": 1,
                }
            }

        results = self.es_client.search(
            index=index_name,
            body={"query": {"knn": knn_query}},
            size=k,
        )

        hits = []
        for hit in results["hits"]["hits"]:
            score = hit["_score"]
            if min_similarity is not None and score < min_similarity:
                continue
            source = hit.get("_source", {})
            metadata = source.get("metadata", {})
            hits.append(
                {
                    "id": str(metadata.get("id") or hit["_id"]),
                    "es_id": hit["_id"],
                    "content": source.get("content") or source.get("text") or source.get("name") or "",
                    "metadata": metadata,
                    "score": score,
                }
            )
        return hits

    def _expand_es_graph(
        self,
        entity_ids: List[str],
        relation_ids: List[str],
        entity_index_name: str,
        relation_index_name: str,
        degree: int,
    ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
        """在 ES 上执行实体-关系的图扩展。

        从种子实体和关系的 ID 出发，通过文档中记录的邻接 metadata
        进行多轮扩展，找到更多相关的实体和关系。

        Args:
            entity_ids: 种子实体 ID 列表
            relation_ids: 种子关系 ID 列表
            entity_index_name: 实体索引名称
            relation_index_name: 关系索引名称
            degree: 扩展轮数

        Returns:
            包含全部实体 ID 列表、全部关系 ID 列表和每步扩展记录的元组
        """
        all_entity_ids = set(entity_ids)
        all_relation_ids = set(relation_ids)
        steps: List[Dict[str, Any]] = []

        relation_ids_from_seed_entities = self._relations_by_entities(
            entity_ids=list(all_entity_ids),
            entity_index_name=entity_index_name,
            relation_index_name=relation_index_name,
        )
        new_relation_ids = relation_ids_from_seed_entities - all_relation_ids
        all_relation_ids.update(new_relation_ids)
        steps.append(
            {
                "step": 0,
                "operation": "entity_to_relation",
                "new_entity_ids": [],
                "new_relation_ids": sorted(new_relation_ids),
            }
        )

        for step in range(1, degree + 1):
            found_entity_ids = self._entities_by_relations(
                relation_ids=list(all_relation_ids), relation_index_name=relation_index_name
            )
            new_entity_ids = found_entity_ids - all_entity_ids
            all_entity_ids.update(new_entity_ids)

            found_relation_ids = self._relations_by_entities(
                entity_ids=list(new_entity_ids),
                entity_index_name=entity_index_name,
                relation_index_name=relation_index_name,
            )
            new_relation_ids = found_relation_ids - all_relation_ids
            all_relation_ids.update(new_relation_ids)

            steps.append(
                {
                    "step": step,
                    "operation": "relation_to_entity_to_relation",
                    "new_entity_ids": sorted(new_entity_ids),
                    "new_relation_ids": sorted(new_relation_ids),
                }
            )

            if not new_entity_ids and not new_relation_ids:
                break

        return sorted(all_entity_ids), sorted(all_relation_ids), steps

    def _relations_by_entities(
        self,
        entity_ids: List[str],
        entity_index_name: str,
        relation_index_name: str,
    ) -> Set[str]:
        """根据实体 ID 查找关联的关系 ID。

        优先从实体文档的 metadata.relation_ids 中获取；若未找到，
        则回退到在关系索引中按 metadata.entity_ids 字段搜索。

        Args:
            entity_ids: 实体 ID 列表
            entity_index_name: 实体索引名称
            relation_index_name: 关系索引名称

        Returns:
            关联的关系 ID 集合
        """
        relation_ids: Set[str] = set()
        for entity in self._get_docs_by_ids(entity_index_name, entity_ids):
            relation_ids.update(self._metadata_list(entity, "relation_ids"))

        if relation_ids:
            return relation_ids

        for relation in self._search_by_terms(
            index_name=relation_index_name,
            field="metadata.entity_ids",
            values=entity_ids,
            size=max(len(entity_ids) * 20, 50),
        ):
            relation_ids.add(relation["id"])
        return relation_ids

    def _entities_by_relations(
        self, relation_ids: List[str], relation_index_name: str
    ) -> Set[str]:
        """根据关系 ID 查找关联的实体 ID。

        从关系文档的 metadata.entity_ids 中提取所有关联的实体 ID。

        Args:
            relation_ids: 关系 ID 列表
            relation_index_name: 关系索引名称

        Returns:
            关联的实体 ID 集合
        """
        entity_ids: Set[str] = set()
        for relation in self._get_docs_by_ids(relation_index_name, relation_ids):
            entity_ids.update(self._metadata_list(relation, "entity_ids"))
        return entity_ids

    def _evict_relations_by_vector(
        self,
        query: str,
        relation_ids: List[str],
        relation_index_name: str,
        limit: int,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """当关系数量超过限制时，用向量相似度裁剪到限定的数量。

        Args:
            query: 查询文本，用于向量排序
            relation_ids: 待裁剪的关系 ID 列表
            relation_index_name: 关系索引名称
            limit: 保留的最大关系数量

        Returns:
            包含保留的关系 ID 列表和裁剪信息字典的元组
        """
        before_count = len(relation_ids)
        if before_count <= limit:
            return sorted(relation_ids), {
                "occurred": False,
                "before_count": before_count,
                "after_count": before_count,
            }

        kept = [
            hit["id"]
            for hit in self._vector_search_raw(
                query=query,
                k=limit,
                index_name=relation_index_name,
                ids=relation_ids,
            )
        ]
        return kept, {
            "occurred": True,
            "before_count": before_count,
            "after_count": len(kept),
        }

    def _search_passages_by_graph(
        self,
        query: str,
        index_name: str,
        relation_ids: List[str],
        entity_ids: List[str],
        k: int,
    ) -> List[Dict[str, Any]]:
        """根据关系 ID、实体 ID 和查询文本从篇章索引中检索相关段落。

        使用 Elasticsearch bool should 查询，将 relation_ids 匹配、
        entity_ids 匹配和文本匹配作为加权子句组合。

        Args:
            query: 查询文本（可选，为空时跳过文本匹配）
            index_name: 篇章索引名称
            relation_ids: 相关关系 ID 列表
            entity_ids: 相关实体 ID 列表
            k: 返回的文档数量

        Returns:
            匹配的篇章文档列表
        """
        should_clauses = []
        if relation_ids:
            should_clauses.append({"terms": {"metadata.relation_ids": relation_ids}})
        if entity_ids:
            should_clauses.append({"terms": {"metadata.entity_ids": entity_ids}})
        if query:
            should_clauses.append(
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^2", "title", "summary"],
                        "type": "best_fields",
                    }
                }
            )

        if not should_clauses:
            return []

        results = self.es_client.search(
            index=index_name,
            body={
                "query": {
                    "bool": {
                        "should": should_clauses,
                        "minimum_should_match": 1,
                    }
                }
            },
            size=k,
        )
        return [self._hit_to_result(hit) for hit in results["hits"]["hits"]]

    def _get_docs_by_ids(self, index_name: str, doc_ids: Iterable[str]    ) -> List[Dict[str, Any]]:
        """根据文档 ID 列表批量获取文档。

        优先使用 ES mget API 按 ID 获取，未命中的 ID 再回退到
        按 metadata.id 字段搜索。

        Args:
            index_name: 目标索引名称
            doc_ids: 文档 ID 的可迭代对象

        Returns:
            文档列表，每项包含 id、content、metadata 等字段
        """
        ids = [doc_id for doc_id in doc_ids if doc_id]
        if not ids:
            return []
        results = self.es_client.mget(index=index_name, ids=ids)
        docs = []
        found_ids = set()
        for doc in results.get("docs", []):
            if not doc.get("found"):
                continue
            source = doc.get("_source", {})
            metadata = source.get("metadata", {})
            found_ids.add(doc["_id"])
            if metadata.get("id") is not None:
                found_ids.add(str(metadata["id"]))
            docs.append(
                {
                    "id": doc["_id"],
                    "content": source.get("content") or source.get("text") or source.get("name") or "",
                    "metadata": metadata,
                }
            )

        missed_ids = [doc_id for doc_id in ids if doc_id not in found_ids]
        docs.extend(
            self._search_by_terms(
                index_name=index_name,
                field="metadata.id",
                values=missed_ids,
                size=len(missed_ids),
            )
        )
        return docs

    def _search_by_terms(
        self, index_name: str, field: str, values: List[str], size: int
    ) -> List[Dict[str, Any]]:
        """按 terms 查询在指定字段上搜索匹配的文档。

        Args:
            index_name: 目标索引名称
            field: 搜索字段名
            values: 要匹配的值列表
            size: 返回的最大文档数量

        Returns:
            匹配的文档列表
        """
        if not values:
            return []
        results = self.es_client.search(
            index=index_name,
            body={"query": {"terms": {field: values}}},
            size=size,
        )
        return [self._hit_to_result(hit) for hit in results["hits"]["hits"]]

    def _hit_to_result(self, hit: Dict[str, Any]) -> Dict[str, Any]:
        """将 ES 原始命中结果转换为统一格式的字典。

        Args:
            hit: ES 搜索命中的原始文档

        Returns:
            统一格式的字典，包含 id、es_id、content、metadata、score 字段
        """
        source = hit.get("_source", {})
        metadata = source.get("metadata", {})
        return {
            "id": str(metadata.get("id") or hit.get("_id")),
            "es_id": hit.get("_id"),
            "content": source.get("content") or source.get("text") or source.get("name") or "",
            "metadata": metadata,
            "score": hit.get("_score"),
        }

    def _ids_from_hits(self, hits: List[Dict[str, Any]]) -> List[str]:
        """从命中结果列表中提取去重后的 ID 列表。

        Args:
            hits: 检索命中文档列表

        Returns:
            去重后的文档 ID 列表
        """
        ids = []
        for hit in hits:
            ids.append(str(hit["id"]))
        return list(dict.fromkeys(ids))

    def _metadata_list(self, doc: Dict[str, Any], key: str) -> List[str]:
        """从文档的元数据中提取指定键的字符串列表。

        Args:
            doc: 文档字典
            key: 元数据中的键名

        Returns:
            字符串列表
        """
        value = doc.get("metadata", {}).get(key, [])
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _simple_extract_entities(self, query: str) -> List[str]:
        """从查询字符串中简单提取候选实体词。

        按中文标点分词后过滤掉单字词和符号，返回最多 8 个候选实体。

        Args:
            query: 查询文本

        Returns:
            候选实体词列表
        """
        words = []
        for raw_word in query.replace("，", " ").replace("。", " ").split():
            word = raw_word.strip("'\".,;:!?()[]{}<>《》、")
            if len(word) >= 2:
                words.append(word)
        return list(dict.fromkeys(words))[:8]

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> str:
        """向索引中添加单个文档。

        自动计算文档内容的嵌入向量并写入 ES 索引。

        Args:
            content: 文档内容
            metadata: 文档元数据字典（可选）
            doc_id: 自定义文档 ID（可选，不传则由 ES 自动生成）
            index_name: 目标索引名称

        Returns:
            写入的文档 ID

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for add operations")
        embedding = self.embedding_model.embed_query(content)
        doc_body = {
            "content": content,
            "embedding": embedding,
            "metadata": metadata or {},
        }
        result = self.es_client.index(
            index=index_name,
            id=doc_id,
            document=doc_body,
            refresh=True,
        )
        logger.info(f"文档添加成功: id={result['_id']}, index={index_name}")
        return result["_id"]

    def add_batch(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
    ) -> List[str]:
        """批量向索引中添加文档。

        使用 ES bulk API 批量写入，自动为每个文档计算嵌入向量。

        Args:
            documents: 文档字典列表，每项应包含 content 和可选的 metadata 字段
            index_name: 目标索引名称

        Returns:
            写入的文档 ID 列表

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for add_batch operations")
        if not documents:
            return []
        operations = []
        for doc in documents:
            content = doc.get("content", "")
            embedding = self.embedding_model.embed_query(content)
            operations.append({"index": {"_index": index_name}})
            operations.append(
                {
                    "content": content,
                    "embedding": embedding,
                    "metadata": doc.get("metadata", {}),
                }
            )

        result = self.es_client.bulk(operations=operations, refresh=True)
        ids = []
        for item in result["items"]:
            ids.append(item["index"]["_id"])
        logger.info(f"批量添加文档成功: 数量={len(ids)}, index={index_name}")
        return ids

    def update(
        self,
        doc_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        index_name: Optional[str] = None,
    ) -> bool:
        """更新索引中的文档。

        当提供新的 content 时自动重新计算嵌入向量。

        Args:
            doc_id: 要更新的文档 ID
            content: 新文档内容（可选）
            metadata: 新文档元数据（可选）
            index_name: 目标索引名称

        Returns:
            更新是否成功

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for update operations")
        update_body: Dict[str, Any] = {}
        if content is not None:
            update_body["content"] = content
            update_body["embedding"] = self.embedding_model.embed_query(content)
        if metadata is not None:
            update_body["metadata"] = metadata

        if not update_body:
            logger.warning(f"文档更新失败: id={doc_id}, 无更新内容")
            return False

        result = self.es_client.update(
            index=index_name,
            id=doc_id,
            doc=update_body,
            refresh=True,
        )
        logger.info(f"文档更新成功: id={doc_id}, index={index_name}")
        return result["result"] in ["updated", "noop"]

    def delete(self, doc_id: str, index_name: Optional[str] = None) -> bool:
        """从索引中删除单个文档。

        Args:
            doc_id: 要删除的文档 ID
            index_name: 目标索引名称

        Returns:
            删除是否成功

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for delete operations")
        result = self.es_client.delete(
            index=index_name,
            id=doc_id,
            refresh=True,
        )
        logger.info(f"文档删除成功: id={doc_id}, index={index_name}")
        return result["result"] == "deleted"

    def delete_batch(
        self, doc_ids: List[str], index_name: Optional[str] = None
    ) -> List[bool]:
        """批量从索引中删除文档。

        使用 ES bulk API 批量删除。

        Args:
            doc_ids: 要删除的文档 ID 列表
            index_name: 目标索引名称

        Returns:
            每个文档的删除结果布尔值列表

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for delete_batch operations")
        if not doc_ids:
            return []

        operations = [
            {"delete": {"_index": index_name, "_id": doc_id}} for doc_id in doc_ids
        ]
        result = self.es_client.bulk(operations=operations, refresh=True)

        results = []
        for item in result["items"]:
            results.append(item["delete"]["result"] == "deleted")
        logger.info(
            f"批量删除文档成功: 成功数={sum(results)}, 失败数={len(results) - sum(results)}, index={index_name}"
        )
        return results

    def delete_by_filter(
        self,
        filter_conditions: dict[str, Any],
        index_names: list[str] | None = None,
    ) -> int:
        """按过滤条件批量删除文档。

        使用 ES delete_by_query API 删除匹配条件的文档。

        Args:
            filter_conditions: 过滤条件 {字段: 值}，支持等值和列表匹配。
            index_names: 目标索引名称列表。

        Returns:
            删除的文档数量。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="delete_by_filter",
        )
        must_clauses: list[dict[str, Any]] = []
        for field, value in filter_conditions.items():
            if isinstance(value, list):
                must_clauses.append({"terms": {field: value}})
            else:
                must_clauses.append({"term": {field: value}})
        response = self.es_client.delete_by_query(
            index=target_indexes,
            body={"query": {"bool": {"must": must_clauses}}},
            refresh=True,
        )
        deleted = response.get("deleted", 0)
        logger.info(f"按条件删除文档成功: 数量={deleted}, index={target_indexes}")
        return deleted

    def get(
        self, doc_id: str, index_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """根据 ID 从索引中获取单个文档。

        Args:
            doc_id: 要获取的文档 ID
            index_name: 目标索引名称

        Returns:
            文档字典，包含 content 和 metadata 字段；不存在时返回 None

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for get operations")
        try:
            result = self.es_client.get(index=index_name, id=doc_id)
            source = result["_source"]
            return {
                "content": source.get("content", ""),
                "metadata": source.get("metadata", {}),
            }
        except Exception as e:
            logger.error(f"获取文档失败: id={doc_id}, error={e}")
            return None

    def batch_get(
        self,
        doc_ids: list[str],
        index_name: str | None = None,
    ) -> list[dict[str, Any] | None]:
        """批量获取文档。

        使用 ES mget API 按 ID 列表批量获取，未命中的 ID 对应位置为 None。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 目标索引名。

        Returns:
            按传入 ID 顺序排列的文档列表，未找到的项为 None。
        """
        if not index_name:
            raise ValueError("index_name is required for batch_get")
        if not doc_ids:
            return []
        results = self.es_client.mget(index=index_name, ids=doc_ids)
        output: list[dict[str, Any] | None] = []
        for doc in results.get("docs", []):
            if not doc.get("found"):
                output.append(None)
            else:
                source = doc.get("_source", {})
                metadata = source.get("metadata", {})
                output.append({
                    "id": str(metadata.get("id") or doc["_id"]),
                    "content": source.get("content", ""),
                    "metadata": metadata,
                })
        logger.info(
            f"批量获取文档: 请求={len(doc_ids)}, 命中={sum(1 for r in output if r is not None)}, index={index_name}"
        )
        return output

    def search(
        self,
        query: str | None = None,
        k: int = 3,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """通用全文检索接口，支持关键词查询和过滤条件。

        当未提供 query 时返回索引中的全部文档。

        Args:
            query: 查询关键词（可选，为空时返回全部文档）。
            k: 返回的文档数量，默认为 3。
            filter_conditions: 过滤条件字典（可选）。
            index_names: 目标索引名称列表。

        Returns:
            匹配文档列表。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="search",
        )
        must_clauses = []
        if query:
            must_clauses.append(
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["content^2", "title", "summary"],
                        "type": "best_fields",
                    }
                }
            )
        if filter_conditions:
            for field, value in filter_conditions.items():
                must_clauses.append({"term": {field: value}})

        search_body: Dict[str, Any] = (
            {"query": {"bool": {"must": must_clauses}}}
            if must_clauses
            else {"query": {"match_all": {}}}
        )

        results = self.es_client.search(index=target_indexes, body=search_body, size=k)
        return [self._hit_to_result(hit) for hit in results["hits"]["hits"]]

    def exists(self, doc_id: str, index_name: Optional[str] = None) -> bool:
        """检查指定 ID 的文档是否存在于索引中。

        Args:
            doc_id: 要检查的文档 ID
            index_name: 目标索引名称

        Returns:
            文档是否存在

        Raises:
            ValueError: 当 index_name 未提供时抛出
        """
        if not index_name:
            raise ValueError("index_name is required for exists operations")
        return self.es_client.exists(index=index_name, id=doc_id)

    def count(
        self,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> int:
        """统计索引中匹配过滤条件的文档数量。

        Args:
            filter_conditions: 过滤条件字典（可选，不传时统计全部文档）。
            index_names: 目标索引名称列表。

        Returns:
            匹配文档的数量。

        Raises:
            ValueError: 当 index_names 未提供时抛出。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="count",
        )
        if filter_conditions:
            must_clauses = [
                {"term": {field: value}} for field, value in filter_conditions.items()
            ]
            search_body = {"query": {"bool": {"must": must_clauses}}}
        else:
            search_body = {"query": {"match_all": {}}}
        result = self.es_client.count(index=target_indexes, body=search_body)
        return result["count"]

    def raw_search(
        self,
        body: dict[str, Any] | None = None,
        *,
        index_names: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """透传原生查询到 ES，返回 ES 原始响应。

        支持 ES 8.x 的 knn 参数、query body 等各种原生查询格式。
        例如：:

            store.raw_search(
                knn={"field": "embedding", "query_vector": vec, "k": 10},
                index_names=["my_index"],
            )

            store.raw_search(
                {"query": {"match": {"content": "hello"}}},
                index_names=["my_index"],
            )

        Args:
            body: ES 查询 body（可选，与 kwargs 中的 knn 等参数二选一）。
            index_names: 目标索引名称列表。
            **kwargs: 透传给 es_client.search 的额外参数（如 knn、_source、size 等）。

        Returns:
            ES 原始 search 响应字典。
        """
        target_indexes = self._resolve_required_indexes(
            index_names,
            operation="raw_search",
        )
        params: dict[str, Any] = {"index": target_indexes}
        if body is not None:
            params["body"] = body
        params.update(kwargs)
        return self.es_client.search(**params)

    def _list_index_names(self) -> list[str]:
        """列出 ES 中所有非系统索引（跳过 . 开头索引）。"""
        result = self.es_client.indices.get_alias(index="*")
        return sorted([idx for idx in result if not idx.startswith(".")])

    def create_index(
        self,
        index_name: str,
        *,
        vector_dim: int | None = None,
        force: bool = False,
    ) -> bool:
        """创建 ES 索引，并预设向量字段 mapping。

        Args:
            index_name: 索引名称。
            vector_dim: 向量维度，为 None 时使用 self.embedding_dimensions。
            force: 为 True 时覆盖已有索引；为 False 时仅当索引不存在时创建。

        Returns:
            是否创建成功。
        """
        if self.es_client.indices.exists(index=index_name):
            if not force:
                logger.info(f"索引已存在，跳过创建: {index_name}")
                return False
            self.es_client.indices.delete(index=index_name)
            logger.info(f"已删除旧索引: {index_name}")

        dim = vector_dim or self.embedding_dimensions or 1536
        mapping = {
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": dim,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {"type": "object", "dynamic": True},
                }
            }
        }
        self.es_client.indices.create(index=index_name, body=mapping)
        logger.info(f"索引创建成功: {index_name}, 向量维度={dim}")
        return True

    def delete_index(self, index_name: str) -> bool:
        """删除 ES 索引。

        Args:
            index_name: 索引名称。

        Returns:
            是否删除成功。
        """
        if not self.es_client.indices.exists(index=index_name):
            logger.warning(f"索引不存在，跳过删除: {index_name}")
            return False
        self.es_client.indices.delete(index=index_name)
        logger.info(f"索引删除成功: {index_name}")
        return True

    def index_exists(self, index_name: str) -> bool:
        """检查 ES 索引是否存在。

        Args:
            index_name: 索引名称。

        Returns:
            索引是否存在。
        """
        return self.es_client.indices.exists(index=index_name)

    def _resolve_refresh_indexes(
        self, *, index_names: list[str] | None = None
    ) -> list[str]:
        """解析 refresh 的目标索引列表。None=全量，空列表抛异常。"""
        if index_names is not None:
            normalized = [name.strip() for name in index_names if name and name.strip()]
            unique = list(dict.fromkeys(normalized))
            if not unique:
                raise ValueError("index_names 不能为空列表")
            return unique
        return self._list_index_names()

    def _init_refresh_batch(self, index_name: str, batch_size: int) -> None:
        """ES 批次初始化：清理该索引的旧 scroll 上下文，防止泄漏。"""
        if not hasattr(self, "_scroll_contexts"):
            self._scroll_contexts = {}
        if index_name in self._scroll_contexts:
            self.es_client.clear_scroll(scroll_id=self._scroll_contexts[index_name])
            del self._scroll_contexts[index_name]

    def _fetch_refresh_batch(
        self, index_name: str, batch_size: int
    ) -> list[dict[str, Any]]:
        """ES 批次获取：scroll 翻页，首次调用发起 search，后续 scroll。"""
        if not hasattr(self, "_scroll_contexts"):
            self._scroll_contexts = {}

        if index_name not in self._scroll_contexts:
            # 首次：发起带 scroll 的 search
            result = self.es_client.search(
                index=index_name,
                body={"query": {"match_all": {}}, "sort": ["_doc"]},
                size=batch_size,
                scroll="5m",
                _source=["content", "metadata.id"],
            )
            self._scroll_contexts[index_name] = result["_scroll_id"]
            hits = result["hits"]["hits"]
        else:
            # 后续：使用 scroll_id 继续翻页
            scroll_id = self._scroll_contexts[index_name]
            result = self.es_client.scroll(scroll_id=scroll_id, scroll="5m")
            hits = result["hits"]["hits"]

        if not hits:
            # 无更多数据，清理 scroll 上下文
            if index_name in self._scroll_contexts:
                self.es_client.clear_scroll(
                    scroll_id=self._scroll_contexts.pop(index_name)
                )
            return []

        return [
            {
                "id": hit["_source"].get("metadata", {}).get("id") or hit["_id"],
                "content": hit["_source"].get("content", ""),
                "index_name": index_name,
            }
            for hit in hits
        ]

    def _ensure_refresh_dimensions(
        self, new_dim: int, index_names: list[str]
    ) -> None:
        """ES 维度适配：读取各索引 mapping 的 embedding.dims，如果与新维度不匹配则标记为需重建。"""
        self._needs_reindex = set()
        for idx in index_names:
            try:
                mapping = self.es_client.indices.get_mapping(index=idx)
                props = mapping[idx]["mappings"]["properties"]
                emb = props.get("embedding", {})
                current_dim = emb.get("dims", 0)
                if current_dim == new_dim:
                    continue
            except Exception:
                pass
            # 维度不一致或读取 mapping 失败时标记为需重建索引
            self._needs_reindex.add(idx)
        self.embedding_dimensions = new_dim

    def _refresh_embeddings_batch(
        self,
        docs: list[dict[str, Any]],
        new_embedding_model,
        index_name: str,
    ) -> tuple[int, int]:
        """ES 批量更新：用 bulk API 逐文档 update embedding 字段。

        不刷新 refresh=False 以提升写入吞吐，维度变化时写入旧的 index，
        后续 _finalize_refresh 会做全量迁移到新索引。
        """
        if not docs:
            return (0, 0)
        try:
            embeddings = new_embedding_model.embed_documents(
                [doc["content"] for doc in docs]
            )
        except Exception:
            logger.error("嵌入失败: {}", [doc.get("id", "unknown") for doc in docs])
            return (0, len(docs))

        # 构造 bulk update operations
        operations = []
        for doc, emb in zip(docs, embeddings):
            operations.append({"update": {"_index": index_name, "_id": doc["id"]}})
            operations.append({"doc": {"embedding": emb}})

        try:
            result = self.es_client.bulk(operations=operations, refresh=False)
        except Exception as exc:
            logger.warning("批量嵌入写入失败: {}", exc)
            return (0, len(docs))

        if not result.get("errors"):
            return (len(docs), 0)

        # 部分失败时逐项检查 error 字段
        success = 0
        fail = 0
        for item in result.get("items", []):
            if "error" in item.get("update", {}):
                fail += 1
            else:
                success += 1
        return (success, fail)

    def _finalize_refresh(self) -> None:
        """ES refresh 收尾：对维度变化的索引做重建迁移。

        流程（每索引独立）：
        1. 读旧索引 setting 和 mapping，更新 embedding.dims
        2. 以 {原名}_v2 建新索引
        3. scroll 旧索引全部文档 → 重新嵌入 → bulk index 到 v2
        4. 删旧索引，建 v2→原名 别名（后续通过别名读写透明迁移）
        """
        if not self._needs_reindex:
            return
        for idx in list(self._needs_reindex):
            v2_name = f"{idx}_v2"
            old_settings = self.es_client.indices.get_settings(index=idx)
            old_mapping = self.es_client.indices.get_mapping(index=idx)
            settings = old_settings[idx]["settings"]["index"]
            mapping_body = old_mapping[idx]["mappings"]

            # 更新 embedding 维度到新值
            if (
                "properties" in mapping_body
                and "embedding" in mapping_body["properties"]
            ):
                mapping_body["properties"]["embedding"]["dims"] = (
                    self.embedding_dimensions
                )

            # 创建新索引 v2，使用新维度的 mapping
            self.es_client.indices.create(
                index=v2_name,
                settings={
                    "number_of_shards": settings.get("number_of_shards", 1),
                    "number_of_replicas": 0,
                },
                mappings=mapping_body,
            )

            # scroll 旧索引全部文档，重新嵌入后写入 v2
            scroll = self.es_client.search(
                index=idx,
                body={"query": {"match_all": {}}, "sort": ["_doc"]},
                size=100,
                scroll="5m",
                _source=True,
            )
            sid = scroll["_scroll_id"]
            while scroll["hits"]["hits"]:
                ops = []
                for hit in scroll["hits"]["hits"]:
                    src = hit["_source"]
                    emb = self.embedding_model.embed_query(src.get("content", ""))
                    src["embedding"] = emb
                    ops.append({"index": {"_index": v2_name, "_id": hit["_id"]}})
                    ops.append(src)
                if ops:
                    self.es_client.bulk(operations=ops, refresh=False)
                scroll = self.es_client.scroll(scroll_id=sid, scroll="5m")
                sid = scroll["_scroll_id"]
            self.es_client.clear_scroll(scroll_id=sid)

            # 删旧物理索引，将别名指向 v2
            self.es_client.indices.delete(index=idx)
            self.es_client.indices.put_alias(index=v2_name, name=idx)

    def refresh_embeddings(
        self,
        new_embedding_model=None,
        *,
        batch_size: int = 50,
        index_names: list[str] | None = None,
    ) -> tuple[int, int]:
        """用新嵌入模型刷新所有已有文档的向量。

        ES 实现：维度不变时直接 bulk update，维度变化时重建索引
        （_finalize_refresh 完成 v2 索引创建 + 别名切换）。
        """
        if new_embedding_model is not None:
            old_model = self._embedding_model
            self._embedding_model = new_embedding_model
        else:
            old_model = None

        success_count = 0
        fail_count = 0
        fail_records: list[dict[str, Any]] = []

        self._needs_reindex = set()

        try:
            probe_embedding = self.embedding_model.embed_query("测试")
            new_dim = len(probe_embedding)
            target_indexes = self._resolve_refresh_indexes(index_names=index_names)
            self._ensure_refresh_dimensions(new_dim, target_indexes)

            for index_name in target_indexes:
                self._init_refresh_batch(index_name, batch_size)
                while True:
                    batch = self._fetch_refresh_batch(index_name, batch_size)
                    if not batch:
                        break
                    try:
                        suc, fail = self._refresh_embeddings_batch(
                            batch, self.embedding_model, index_name
                        )
                        success_count += suc
                        fail_count += fail
                    except Exception as exc:
                        fail_count += len(batch)
                        for doc in batch:
                            fail_records.append({
                                "id": doc.get("id", "unknown"),
                                "index_name": index_name,
                                "content_preview": doc.get("content", "")[:100],
                                "error": str(exc),
                            })
        finally:
            if old_model is not None:
                self._embedding_model = old_model

        if fail_records:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fail_path = self._refresh_fail_dir / f"refresh_failed_{ts}.jsonl"
            self._refresh_fail_dir.mkdir(parents=True, exist_ok=True)
            with open(fail_path, "w", encoding="utf-8") as f:
                for rec in fail_records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        self._finalize_refresh()
        return success_count, fail_count
