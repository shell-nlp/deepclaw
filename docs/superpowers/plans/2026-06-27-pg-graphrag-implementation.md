# PG GraphRAG 实现计划

> **For agentic workers:** 使用 subagent-driven-development 逐任务实现。步骤使用 `- [ ]` 语法追踪进度。

**目标：** 创建基于 `AbstractVectorStore` 的 PG GraphRAG 实现，并通过工厂函数实现一键切换后端。

**架构：** 抽取 `BaseGraphRAG` ABC 承载共享逻辑（图构建、三元组抽取、CRUD 编排），两个子类各自实现后端的检索与批量写入。

**Tech Stack:** Python 3.12+, PostgreSQL 16+, pgvector, psycopg, FastAPI

## 全局约束

- 不改动现有 `ElasticsearchVectorStore.vector_graph_retrieve` 路径
- `BaseGraphRAG` 只依赖 `AbstractVectorStore` 接口
- 所有新增代码必须通过 `ruff check .`
- 所有新增文件必须通过 `python -m py_compile`
- 保持 `ElasticGraphRAG(es, graph_name, chat_model)` 的构造签名向后兼容
- 使用 `typing` 类型标注，不用 `from __future__ import annotations` 以外的未来导入

---

### Task 1: 为 AbstractVectorStore.vector_search 增加 filter_conditions

**Files:**
- Modify: `deepclaw/common/vector_store/base.py:46-60`

**Interfaces:**
- Produces: `AbstractVectorStore.vector_search(self, query, k=3, index_name=None, index_names=None, min_similarity=None, filter_conditions=None)` — 新增 `filter_conditions: dict | None` 参数

- [ ] **Step 1: 读取 base.py 定位 vector_search 方法**

```bash
uv run python -m py_compile deepclaw/common/vector_store/base.py
```

- [ ] **Step 2: 修改 vector_search 签名增加 filter_conditions**

```python
# 原始签名（找到对应位置修改）
@abstractmethod
def vector_search(
    self,
    query: str,
    k: int = 3,
    index_name: str | None = None,
    index_names: list[str] | None = None,
    min_similarity: float | None = None,
    filter_conditions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ...
```

- [ ] **Step 3: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/vector_store/base.py
```

- [ ] **Step 4: 提交**

```bash
git add deepclaw/common/vector_store/base.py
git commit -m "feat: add filter_conditions param to AbstractVectorStore.vector_search"
```

---

### Task 2: 实现 PgVectorStore.vector_search 的 filter_conditions

**Files:**
- Modify: `deepclaw/common/vector_store/pgsql.py:442-466`

**Interfaces:**
- Consumes: `AbstractVectorStore.vector_search(... filter_conditions=...)` 签名
- Produces: `PgVectorStore.vector_search()` 支持 `filter_conditions` — 当 key 以 `metadata.` 开头且值为列表时使用 jsonb 数组包含 `@>`；否则使用等值匹配

- [ ] **Step 1: 读取 pgsql.py 理解 vector_search 实现**

```bash
uv run python -m py_compile deepclaw/common/vector_store/pgsql.py
```

- [ ] **Step 2: 实现 filter_conditions 支持**

修改 `PgVectorStore.vector_search()` 方法，在 `_fetch_vector_candidates` 的 SQL 中添加 WHERE 子句：

```python
def vector_search(
    self,
    query: str,
    k: int = 3,
    index_name: str | None = None,
    index_names: list[str] | None = None,
    min_similarity: float | None = None,
    filter_conditions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    target_indexes = self._resolve_read_indexes(index_name=index_name, index_names=index_names)
    if not target_indexes:
        return []

    query_vector = self.embedding_model.embed_query(query)
    self._ensure_embedding_dimensions(query_vector)
    candidates: list[dict[str, Any]] = []
    for target_index in target_indexes:
        rows = self._fetch_vector_candidates(
            index_name=target_index,
            query_vector=query_vector,
            limit=max(k, 8),
            filter_conditions=filter_conditions,
        )
        candidates.extend(self._row_to_result(row) for row in rows)
    candidates = self._apply_min_similarity(candidates, min_similarity)
    candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return candidates[:k]
```

然后修改 `_fetch_vector_candidates` 增加 `filter_conditions` 参数：

```python
def _fetch_vector_candidates(
    self,
    *,
    index_name: str,
    query_vector: list[float],
    limit: int,
    filter_conditions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    self._ensure_base_schema()
    self._ensure_partition(index_name)
    partition_table = self._qualified_partition_name(index_name)

    where_clauses: list[str] = []
    params: dict[str, Any] = {
        "index_name": index_name,
        "query_vector": query_vector,
        "limit": limit,
    }
    if filter_conditions:
        for idx, (field, value) in enumerate(filter_conditions.items()):
            param_name = f"filter_{idx}"
            if field.startswith("metadata."):
                metadata_key = field.split(".", 1)[1]
                if isinstance(value, list):
                    # 数组包含：metadata -> 'entity_ids' @> '["id1"]'::jsonb
                    where_clauses.append(
                        f"(metadata -> '{metadata_key}') @> %({param_name})s::jsonb"
                    )
                    params[param_name] = str(value)
                else:
                    where_clauses.append(
                        f"metadata ->> '{metadata_key}' = %({param_name})s"
                    )
                    params[param_name] = str(value)
            else:
                where_clauses.append(f"{field} = %({param_name})s")
                params[param_name] = str(value)

    where_sql = f" AND {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"""
    SELECT
        id,
        %(index_name)s AS index_name,
        content,
        metadata,
        1 - (embedding <=> %(query_vector)s) AS score
    FROM {partition_table}
    WHERE 1=1{where_sql}
    ORDER BY embedding <=> %(query_vector)s
    LIMIT %(limit)s
    """

    with self._connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
```

- [ ] **Step 3: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/vector_store/pgsql.py
```

- [ ] **Step 4: 提交**

```bash
git add deepclaw/common/vector_store/pgsql.py
git commit -m "feat: implement filter_conditions in PgVectorStore.vector_search"
```

---

### Task 3: 兼容 ElasticsearchVectorStore.vector_search 的 filter_conditions

**Files:**
- Modify: `deepclaw/common/vector_store/elasticsearch.py` — 在 `vector_search` 签名中增加 `filter_conditions` 参数（仅接受不处理，ES 图检索走自己的 `vector_graph_retrieve` 路径）

- [ ] **Step 1: 读取 elasticsearch.py 定位 vector_search**

- [ ] **Step 2: 增加 filter_conditions 参数**

在 `vector_search()` 签名中增加 `filter_conditions: dict[str, Any] | None = None`，传入 `_vector_search_raw`。

同时需要确保 `_vector_search_raw` 也接受该参数，在 ES query body 中转化为 `term` 或 `terms` 过滤：

```python
def _vector_search_raw(
    self,
    query_embedding: list[float],
    k: int,
    index_name: str,
    doc_ids: list[str] | None = None,
    filter_conditions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    must_clauses = []
    if doc_ids:
        must_clauses.append({"terms": {"_id": doc_ids}})
    if filter_conditions:
        for field, value in filter_conditions.items():
            if isinstance(value, list):
                must_clauses.append({"terms": {field: value}})
            else:
                must_clauses.append({"term": {field: value}})

    body: dict = {"size": k, "query": {"script_score": {"query": {"bool": {"must": [{"match_all": {}}]}}, "script": {"source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0", "params": {"query_vector": query_embedding}}}}}
    if must_clauses:
        body["query"]["script_score"]["query"]["bool"]["must"] = must_clauses

    # ... 原有搜索逻辑
```

实际需要读取文件后精确修改。这里标记为需在实现时根据实际代码调整。

- [ ] **Step 3: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/vector_store/elasticsearch.py
```

- [ ] **Step 4: 提交**

```bash
git add deepclaw/common/vector_store/elasticsearch.py
git commit -m "feat: accept filter_conditions in ES vector_search"
```

---

### Task 4: 抽取 BaseGraphRAG 抽象基类

**Files:**
- Modify: `deepclaw/common/elastic_graph_rag.py` — 在同一文件中定义 `BaseGraphRAG` ABC，然后让 `ElasticGraphRAG` 继承它
- Modify: `deepclaw/common/__init__.py` — 导出 `BaseGraphRAG`

**Interfaces:**
- Produces: `BaseGraphRAG` ABC 包含：
  - `__init__(self, vector_store: AbstractVectorStore, graph_name: str, chat_model=None)` — 构造时设置 `self.vector_store`、`self.graph_name`、`self.chat_model`、`self.indexes`
  - `index_names(prefix) -> dict` (@staticmethod)
  - `add_texts(texts, metadatas=None, ids=None, extract_triplets=True)` — 对外入口
  - `add_documents(documents, extract_triplets=True)` — 对外入口
  - `delete_graph(ignore_missing=True)` — 调用 `_delete_indexes_internal()`
  - `delete_documents(doc_ids)` — 调用 `_search_by_terms()`、`_delete_or_detach_by_passage_ids()`、`_detach_relation_ids_from_entities()`
  - `delete_by_query(query)` — 先检索再删除
  - `build_graph(documents, extract_triplets=True)` — 图构建逻辑（全量共享）
  - `retrieve(...)` → @abstractmethod
  - `_bulk_index(index_name, docs)` → @abstractmethod
  - `_delete_indexes_internal(index_name)` → @abstractmethod
  - `_delete_docs_internal(index_name, doc_ids)` → @abstractmethod
  - `_search_by_terms(index_name, field, values, size)` → @abstractmethod
  - `_delete_or_detach_by_passage_ids(index_name, docs, deleted_passage_ids)` → @abstractmethod
  - `_detach_relation_ids_from_entities(relation_ids)` → @abstractmethod
  - 所有 `_build_*_docs`、`_get_document_triplets`、`_extract_triplets`、`_extract_query_entities`、`_parse_triplets`、`_get_entity_id`、`_stable_id`、`_normalize`、`_simple_extract_entities` → 共享具体方法
  - `_get_chat_model()` → 共享具体方法
- Produces: 重构后的 `ElasticGraphRAG(BaseGraphRAG)` 保持原构造签名 `(es, graph_name, chat_model=None)` 并保留 `self.es` 属性

- [ ] **Step 1: 读取 elastic_graph_rag.py 完整内容**

- [ ] **Step 2: 在同一文件中定义 BaseGraphRAG ABC**

在 `ElasticGraphRAG` 类定义之前插入 `BaseGraphRAG`：

```python
from abc import ABC, abstractmethod
from deepclaw.common.vector_store.base import AbstractVectorStore

class BaseGraphRAG(ABC):
    """GraphRAG 抽象基类，共享图构建与 CRUD 编排逻辑。"""

    def __init__(
        self,
        vector_store: AbstractVectorStore,
        graph_name: str,
        chat_model=None,
    ):
        self.vector_store = vector_store
        self.graph_name = graph_name
        self.chat_model = chat_model
        self.indexes = self.index_names(graph_name)

    @staticmethod
    def index_names(prefix: str) -> dict[str, str]:
        return {
            "passage": f"{prefix}_passages",
            "entity": f"{prefix}_entities",
            "relation": f"{prefix}_relations",
        }

    # ---- 对外入口 ----
    def add_texts(self, texts, metadatas=None, ids=None, extract_triplets=True) -> dict[str, Any]:
        documents = []
        for index, text in enumerate(texts):
            metadata = metadatas[index] if metadatas and index < len(metadatas) else {}
            doc_id = ids[index] if ids and index < len(ids) else str(uuid.uuid4())
            documents.append(Document(page_content=text, metadata=metadata, id=doc_id))
        return self.add_documents(documents, extract_triplets=extract_triplets)

    def add_documents(self, documents, extract_triplets=True) -> dict[str, Any]:
        """外部入口：构建图 → 批量索引写入。"""
        graph = self.build_graph(documents, extract_triplets=extract_triplets)
        self._bulk_index(self.indexes["entity"], graph["entities"])
        self._bulk_index(self.indexes["relation"], graph["relations"])
        self._bulk_index(self.indexes["passage"], graph["passages"])
        result = {
            "graph_name": self.graph_name,
            "indexes": self.indexes,
            "passage_count": len(graph["passages"]),
            "entity_count": len(graph["entities"]),
            "relation_count": len(graph["relations"]),
        }
        logger.info("向量图索引完成: {}", result)
        return result

    def delete_graph(self, ignore_missing=True) -> dict[str, Any]:
        deleted = {}
        for kind, index_name in self.indexes.items():
            try:
                self._delete_indexes_internal(index_name)
                deleted[kind] = "deleted"
            except Exception:
                if not ignore_missing:
                    raise
                deleted[kind] = "missing"
        return {
            "graph_name": self.graph_name,
            "indexes": self.indexes,
            "result": deleted,
        }

    def delete_documents(self, doc_ids: list[str]) -> dict[str, Any]:
        doc_ids = [str(doc_id) for doc_id in doc_ids if doc_id]
        if not doc_ids:
            return {"deleted_passages": 0, "deleted_relations": 0, "deleted_entities": 0}

        relations = self._search_by_terms(
            self.indexes["relation"], "metadata.passage_ids", doc_ids, size=10000
        )
        entities = self._search_by_terms(
            self.indexes["entity"], "metadata.passage_ids", doc_ids, size=10000
        )

        deleted_passages = self._delete_docs_internal(self.indexes["passage"], doc_ids)
        deleted_relations, kept_relation_ids = self._delete_or_detach_by_passage_ids(
            index_name=self.indexes["relation"],
            docs=relations,
            deleted_passage_ids=doc_ids,
        )
        deleted_entities, _ = self._delete_or_detach_by_passage_ids(
            index_name=self.indexes["entity"],
            docs=entities,
            deleted_passage_ids=doc_ids,
        )

        if deleted_relations:
            self._detach_relation_ids_from_entities(deleted_relations)

        return {
            "deleted_passages": deleted_passages,
            "deleted_relations": len(deleted_relations),
            "deleted_entities": len(deleted_entities),
            "detached_relations": len(kept_relation_ids),
        }

    def delete_by_query(self, query: str) -> dict[str, Any]:
        result = self.retrieve(query=query, k=100, return_debug=False)
        doc_ids = [
            str(doc.get("metadata", {}).get("id") or doc.get("id")) for doc in result
        ]
        return self.delete_documents(doc_ids)

    # ---- 图构建（全量共享） ----
    def build_graph(self, documents, extract_triplets=True) -> dict[str, list[dict[str, Any]]]:
        # 完全复制 ElasticGraphRAG.build_graph 实现
        # ...（所有图构建逻辑，与 ElasticGraphRAG 现有代码一致）

    # ---- _build_*_docs 方法 ----
    # 全部复制自 ElasticGraphRAG

    # ---- 三元组相关 ----
    # _get_document_triplets, _extract_triplets, _extract_query_entities,
    # _parse_triplets, _get_entity_id, _stable_id, _normalize, _simple_extract_entities

    # ---- 工具方法 ----
    def _get_chat_model(self):
        if self.chat_model is None:
            self.chat_model = get_chat_model()
        return self.chat_model

    # ---- 抽象方法 ----
    @abstractmethod
    def retrieve(self, query, k=6, entity_top_k=5, relation_top_k=8,
                  expansion_degree=1, relation_limit=30, return_debug=False):
        ...

    @abstractmethod
    def _bulk_index(self, index_name: str, docs: list[dict]) -> None:
        ...

    @abstractmethod
    def _delete_indexes_internal(self, index_name: str) -> None:
        ...

    @abstractmethod
    def _delete_docs_internal(self, index_name: str, doc_ids: list[str]) -> int:
        ...

    @abstractmethod
    def _search_by_terms(self, index_name: str, field: str, values: list[str], size: int) -> list[dict]:
        ...

    @abstractmethod
    def _delete_or_detach_by_passage_ids(self, index_name: str, docs: list[dict], deleted_passage_ids: list[str]) -> tuple[list[str], list[str]]:
        ...

    @abstractmethod
    def _detach_relation_ids_from_entities(self, relation_ids: list[str]) -> None:
        ...
```

- [ ] **Step 3: 改造 ElasticGraphRAG 继承 BaseGraphRAG**

```python
class ElasticGraphRAG(BaseGraphRAG):
    """基于 Elasticsearch 的轻量 Vector Graph RAG。"""

    def __init__(self, es: ElasticsearchVectorStore, graph_name: str, chat_model=None):
        super().__init__(vector_store=es, graph_name=graph_name, chat_model=chat_model)
        self.es = es  # 保留 ES 专属引用

    def retrieve(self, query, k=6, entity_top_k=5, relation_top_k=8,
                  expansion_degree=1, relation_limit=30, return_debug=False):
        query_entities = self._extract_query_entities(query)
        return self.es.vector_graph_retrieve(
            query=query, k=k, index_name=self.indexes["passage"],
            entity_index_name=self.indexes["entity"],
            relation_index_name=self.indexes["relation"],
            entity_top_k=entity_top_k, relation_top_k=relation_top_k,
            expansion_degree=expansion_degree, relation_limit=relation_limit,
            query_entities=query_entities, return_debug=return_debug,
        )

    def _bulk_index(self, index_name: str, docs: list[dict]) -> None:
        # 从原 _bulk_upsert 搬过来
        ...

    def _delete_indexes_internal(self, index_name: str) -> None:
        if self.es.es_client.indices.exists(index=index_name):
            self.es.es_client.indices.delete(index=index_name)

    def _delete_docs_internal(self, index_name: str, doc_ids: list[str]) -> int:
        # 从原 _delete_ids 搬过来
        ...

    def _search_by_terms(self, index_name: str, field: str, values: list[str], size: int) -> list[dict]:
        # 从原 _search_by_terms 搬过来
        ...

    def _delete_or_detach_by_passage_ids(self, index_name: str, docs, deleted_passage_ids):
        # 从原 _delete_or_detach_by_passage_ids 搬过来
        ...

    def _detach_relation_ids_from_entities(self, relation_ids):
        # 从原 _detach_relation_ids_from_entities 搬过来
        ...
```

需要将以下私有方法从 `ElasticGraphRAG` 移到 `BaseGraphRAG`（因为它们不依赖 ES）：
- `_build_entity_docs`, `_build_relation_docs`, `_build_passage_docs`
- `_get_document_triplets`, `_extract_triplets`, `_extract_query_entities`, `_parse_triplets`
- `_get_entity_id`, `_stable_id`, `_normalize`, `_simple_extract_entities`
- `_get_chat_model`

并将以下 ES 专属方法留在 `ElasticGraphRAG` 作为抽象方法实现：
- `_bulk_upsert` → 改名为 `_bulk_index`
- `_ensure_index`
- `_delete_ids` → 改名为 `_delete_docs_internal`
- `_delete_or_detach_by_passage_ids`
- `_detach_relation_ids_from_entities`
- `_search_by_terms`

同时将 `retrieve` 抽象/重写。

**注意：** 这步重构需要非常小心地移动代码。`build_graph`、`_build_entity_docs`、`_build_relation_docs`、`_build_passage_docs`、`_get_document_triplets`、`_extract_triplets`、`_extract_query_entities`、`_parse_triplets`、`_get_entity_id`、`_stable_id`、`_normalize`、`_simple_extract_entities`、`_get_chat_model` 这些方法必须从 ElasticGraphRAG 的当前代码完整复制到 BaseGraphRAG（保持代码不变，仅修改 `self.es` 引用为 `self.vector_store` 或删除 ES 依赖）。

- [ ] **Step 4: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/elastic_graph_rag.py
```

- [ ] **Step 5: 更新 __init__.py 导出 BaseGraphRAG**

```python
# 在 deepclaw/common/__init__.py 中
from deepclaw.common.elastic_graph_rag import BaseGraphRAG, ElasticGraphRAG
```

- [ ] **Step 6: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/__init__.py
```

- [ ] **Step 7: 运行 ruff 检查**

```bash
uv run ruff check deepclaw/common/elastic_graph_rag.py deepclaw/common/__init__.py
```

- [ ] **Step 8: 提交**

```bash
git add deepclaw/common/elastic_graph_rag.py deepclaw/common/__init__.py
git commit -m "refactor: extract BaseGraphRAG ABC from ElasticGraphRAG"
```

---

### Task 5: 创建 PgGraphRAG

**Files:**
- Create: `deepclaw/common/pg_graph_rag.py`
- Modify: `deepclaw/common/__init__.py` — 导出 `PgGraphRAG`

**Interfaces:**
- Consumes: `BaseGraphRAG` ABC, `PgVectorStore`, `AbstractVectorStore.vector_search` with `filter_conditions`
- Produces: `PgGraphRAG(BaseGraphRAG)` — 完整的 PG 图 RAG 实现

- [ ] **Step 1: 创建 pg_graph_rag.py**

```python
from typing import Any
from collections import defaultdict
from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore
from deepclaw.common.elastic_graph_rag import BaseGraphRAG


class PgGraphRAG(BaseGraphRAG):
    """基于 PostgreSQL pgvector 的轻量 Vector Graph RAG。"""

    def __init__(
        self,
        vector_store: PgVectorStore,
        graph_name: str,
        chat_model=None,
    ):
        super().__init__(vector_store=vector_store, graph_name=graph_name, chat_model=chat_model)
        self.pg = vector_store

    def retrieve(
        self,
        query: str,
        k: int = 6,
        entity_top_k: int = 5,
        relation_top_k: int = 8,
        expansion_degree: int = 1,
        relation_limit: int = 30,
        return_debug: bool = False,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """基于 AbstractVectorStore 接口的应用层图遍历检索。"""
        query_entities = self._extract_query_entities(query)

        # 1. 种子实体检索
        seed_entities = self.vector_store.vector_search(
            query=query,
            k=entity_top_k,
            index_name=self.indexes["entity"],
        )
        entity_ids = [d["id"] for d in seed_entities if d.get("id")]

        # 同时尝试用查询实体名搜索
        for entity_text in query_entities:
            extra = self.vector_store.vector_search(
                query=entity_text,
                k=entity_top_k,
                index_name=self.indexes["entity"],
            )
            for d in extra:
                if d.get("id") and d["id"] not in entity_ids:
                    entity_ids.append(d["id"])

        # 2. 种子关系检索
        seed_relations = self.vector_store.vector_search(
            query=query,
            k=relation_top_k,
            index_name=self.indexes["relation"],
        )
        relation_ids = [d["id"] for d in seed_relations if d.get("id")]

        # 3. 多跳扩展
        expanded_entity_ids = set(entity_ids)
        expanded_relation_ids = set(relation_ids)
        expansion_steps = []
        for degree in range(expansion_degree + 1):
            step_info: dict[str, Any] = {"degree": degree}
            if degree > 0:
                # 从关系找新实体
                if expanded_relation_ids:
                    new_entities = self.vector_store.vector_search(
                        query=query,
                        k=relation_top_k * 2,
                        index_name=self.indexes["entity"],
                        filter_conditions={
                            "metadata.relation_ids": list(expanded_relation_ids),
                        },
                    )
                    for d in new_entities:
                        expanded_entity_ids.add(d["id"])
                    step_info["new_entities_from_relations"] = len(new_entities)

                # 从实体找新关系
                if expanded_entity_ids:
                    new_relations = self.vector_store.vector_search(
                        query=query,
                        k=entity_top_k * 2,
                        index_name=self.indexes["relation"],
                        filter_conditions={
                            "metadata.entity_ids": list(expanded_entity_ids),
                        },
                    )
                    for d in new_relations:
                        expanded_relation_ids.add(d["id"])
                    step_info["new_relations_from_entities"] = len(new_relations)

            expansion_steps.append(step_info)

        # 4. 关系向量裁剪 — 用关系文本再做一次向量搜索，只保留 top-N
        kept_relation_ids = list(expanded_relation_ids)
        if len(kept_relation_ids) > relation_limit:
            reranked = self.vector_store.vector_search(
                query=query,
                k=relation_limit,
                index_name=self.indexes["relation"],
            )
            kept_relation_ids = [d["id"] for d in reranked if d.get("id")]

        # 5. 最终 passage 召回
        passages = self.vector_store.vector_search(
            query=query,
            k=k,
            index_name=self.indexes["passage"],
            filter_conditions={
                "metadata.relation_ids": kept_relation_ids,
            },
        )

        # 如果 passage 不足，补充实体搜索
        if len(passages) < k and expanded_entity_ids:
            extra_passages = self.vector_store.vector_search(
                query=query,
                k=k - len(passages),
                index_name=self.indexes["passage"],
                filter_conditions={
                    "metadata.entity_ids": list(expanded_entity_ids),
                },
            )
            seen_ids = {p["id"] for p in passages}
            for p in extra_passages:
                if p.get("id") not in seen_ids:
                    passages.append(p)

        # 6. 回退
        if not passages:
            passages = self.vector_store.vector_search(
                query=query, k=k, index_name=self.indexes["passage"]
            )

        if not return_debug:
            return passages[:k]

        return {
            "query": query,
            "query_entities": query_entities,
            "passages": passages[:k],
            "seed_entity_ids": list(expanded_entity_ids),
            "seed_relation_ids": list(expanded_relation_ids),
            "expansion_steps": expansion_steps,
            "kept_relation_ids": kept_relation_ids,
        }

    def _bulk_index(self, index_name: str, docs: list[dict]) -> None:
        if not docs:
            return
        self.pg.add_batch(documents=docs, index_name=index_name)

    def _delete_indexes_internal(self, index_name: str) -> None:
        """删除指定 index_name 的所有文档行。"""
        rows = self.pg.search(index_names=[index_name])
        if rows:
            ids = [r["id"] for r in rows]
            self.pg.delete_batch(doc_ids=ids, index_name=index_name)

    def _delete_docs_internal(self, index_name: str, doc_ids: list[str]) -> int:
        if not doc_ids:
            return 0
        results = self.pg.delete_batch(doc_ids=doc_ids, index_name=index_name)
        return sum(1 for r in results if r)

    def _search_by_terms(
        self,
        index_name: str,
        field: str,
        values: list[str],
        size: int,
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        # 用 search 方法通过 filter_conditions 查询
        metadata_key = field.split(".", 1)[1] if field.startswith("metadata.") else field
        results: list[dict[str, Any]] = []
        for value in values:
            batch = self.pg.search(
                index_name=index_name,
                filter_conditions={field: value},
            )
            for item in batch:
                if item not in results:
                    results.append(item)
                if len(results) >= size:
                    break
            if len(results) >= size:
                break
        return results[:size]

    def _delete_or_detach_by_passage_ids(
        self,
        index_name: str,
        docs: list[dict[str, Any]],
        deleted_passage_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        deleted_ids: list[str] = []
        kept_ids: list[str] = []
        deleted_set = set(deleted_passage_ids)

        for doc in docs:
            metadata = dict(doc.get("metadata", {}))
            remaining = [
                pid for pid in metadata.get("passage_ids", [])
                if pid not in deleted_set
            ]
            if remaining:
                metadata["passage_ids"] = remaining
                self.pg.update(
                    doc_id=doc["id"],
                    metadata=metadata,
                    index_name=index_name,
                )
                kept_ids.append(doc["id"])
            else:
                self.pg.delete(doc_id=doc["id"], index_name=index_name)
                deleted_ids.append(doc["id"])

        return deleted_ids, kept_ids

    def _detach_relation_ids_from_entities(self, relation_ids: list[str]) -> None:
        if not relation_ids:
            return
        relation_set = set(relation_ids)
        entities = self._search_by_terms(
            self.indexes["entity"],
            "metadata.relation_ids",
            relation_ids,
            size=10000,
        )
        for entity in entities:
            metadata = dict(entity.get("metadata", {}))
            metadata["relation_ids"] = [
                rid for rid in metadata.get("relation_ids", [])
                if rid not in relation_set
            ]
            self.pg.update(
                doc_id=entity["id"],
                metadata=metadata,
                index_name=self.indexes["entity"],
            )
```

- [ ] **Step 2: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/pg_graph_rag.py
```

- [ ] **Step 3: 更新 __init__.py 导出**

```python
# deepclaw/common/__init__.py
from deepclaw.common.elastic_graph_rag import BaseGraphRAG, ElasticGraphRAG
from deepclaw.common.pg_graph_rag import PgGraphRAG
```

- [ ] **Step 4: 运行 ruff 检查**

```bash
uv run ruff check .
```

- [ ] **Step 5: 提交**

```bash
git add deepclaw/common/pg_graph_rag.py deepclaw/common/__init__.py
git commit -m "feat: add PgGraphRAG implementation"
```

---

### Task 6: 工厂函数 create_graph_rag + 集成到使用处

**Files:**
- Modify: `deepclaw/common/__init__.py` — 添加 `create_graph_rag()`
- Modify: `deepclaw/middleware/rag.py:339-341` — 使用工厂函数
- Modify: `deepclaw/web_backend/knowledge_bases/service.py:233,396,460` — 使用工厂函数
- Modify: `deepclaw/tools/retriever.py:44` — 使用工厂函数

- [ ] **Step 1: 在 __init__.py 中添加工厂函数**

```python
from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore


def create_graph_rag(
    vector_store: AbstractVectorStore,
    graph_name: str,
    chat_model=None,
) -> BaseGraphRAG:
    """根据向量库类型自动创建对应的 GraphRAG 实例。"""
    if isinstance(vector_store, ElasticsearchVectorStore):
        return ElasticGraphRAG(vector_store, graph_name, chat_model)
    if isinstance(vector_store, PgVectorStore):
        return PgGraphRAG(vector_store, graph_name, chat_model)
    raise ValueError(f"不支持的向量库类型: {type(vector_store).__name__}")
```

- [ ] **Step 2: 修改 middleware/rag.py**

```python
# 替换：
# if isinstance(self.vector_store, ElasticsearchVectorStore):
#     rag = ElasticGraphRAG(self.vector_store, graph_name)
# 为：
from deepclaw.common import create_graph_rag

# ...
rag = create_graph_rag(self.vector_store, graph_name)
```

删除顶部 `from deepclaw.common.elastic_graph_rag import ElasticGraphRAG`（如果不再使用）。

- [ ] **Step 3: 修改 knowledge_bases/service.py**

```python
# 替换所有 3 处：
# rag = ElasticGraphRAG(self.es, knowledge_base.index_prefix)
# 为：
rag = create_graph_rag(self.es, knowledge_base.index_prefix)
```

删除顶部 `from deepclaw.common.elastic_graph_rag import ElasticGraphRAG`。

- [ ] **Step 4: 修改 tools/retriever.py**

```python
# 替换：
# rag = ElasticGraphRAG(es=es, graph_name=graph_name)
# 为：
rag = create_graph_rag(es, graph_name)
```

删除顶部 `from deepclaw.common.elastic_graph_rag import ElasticGraphRAG`。

- [ ] **Step 5: 编译验证**

```bash
uv run python -m py_compile deepclaw/common/__init__.py
uv run python -m py_compile deepclaw/middleware/rag.py
uv run python -m py_compile deepclaw/web_backend/knowledge_bases/service.py
uv run python -m py_compile deepclaw/tools/retriever.py
```

- [ ] **Step 6: ruff 检查**

```bash
uv run ruff check .
```

- [ ] **Step 7: 提交**

```bash
git add deepclaw/common/__init__.py deepclaw/middleware/rag.py deepclaw/web_backend/knowledge_bases/service.py deepclaw/tools/retriever.py
git commit -m "feat: add create_graph_rag factory and integrate"
```

---

### Task 7: 验证与更新文档

**Files:**
- Modify: `AGENTS.md` — 记录新文件 `pg_graph_rag.py` 和工厂函数

- [ ] **Step 1: 更新 AGENTS.md**

在 `AGENTS.md` 的 `当前代码结构 > 核心能力层` 部分添加：

```markdown
- `deepclaw/common/pg_graph_rag.py`
  PostgreSQL pgvector 版 GraphRAG，继承 BaseGraphRAG，检索基于 AbstractVectorStore 接口实现图遍历。
```

在 `文件变更清单` 部分或相关位置记录工厂函数。

- [ ] **Step 2: 运行 codegraph 索引**

```bash
codegraph index --force
```

- [ ] **Step 3: 最终验证**

```bash
uv run ruff check .
```

- [ ] **Step 4: 提交**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with PgGraphRAG and factory"
```
