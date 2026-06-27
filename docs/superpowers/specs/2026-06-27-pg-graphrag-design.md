# PG GraphRAG 设计方案

## 背景

当前 `deepclaw/common/elastic_graph_rag.py` 中的 `ElasticGraphRAG` 直接依赖 `ElasticsearchVectorStore`，
无法在 PostgreSQL 或其他向量库后端上运行。前面已完成向量库的抽象接口 `AbstractVectorStore`，现在需要
在此基础上实现一套可切换后端的 GraphRAG 能力。

## 设计目标

1. **可切换**：通过一行配置切换后端（ES ↔ PG ↔ 未来其他）
2. **最小侵入**：不改动现有 ES 路径的已稳定逻辑
3. **接口优先**：图遍历逻辑基于 `AbstractVectorStore` 公共接口，而非具体后端 API

## 整体架构

```
BaseGraphRAG                                ← 共享逻辑（抽象基类）
├── ElasticGraphRAG(BaseGraphRAG)            ← ES：现有路径保持不动
│   └── retrieve() → ES.vector_graph_retrieve()
│   └── _bulk_index() → ES bulk API
│   └── _delete_indexes_internal() → ES indices.delete
│   └── _delete_docs_internal() → ES bulk delete
│   └── _search_by_terms() → ES terms query
│   └── _delete_or_detach_by_passage_ids() → ES update/delete
│   └── _detach_relation_ids_from_entities() → ES update
└── PgGraphRAG(BaseGraphRAG)                ← 新增：基于 PgVectorStore
    └── retrieve() → 应用层图遍历，只用 AbstractVectorStore
    └── _bulk_index() → PgVectorStore.add_batch()
    └── _delete_indexes_internal() → 按 index_name 删表行
    └── _delete_docs_internal() → PgVectorStore.delete_batch()
    └── _search_by_terms() → SQL IN 查询
    └── _delete_or_detach_by_passage_ids() → SQL 更新/删除
    └── _detach_relation_ids_from_entities() → SQL 更新
```

## BaseGraphRAG 职责（共享逻辑）

所有与具体后端无关的代码提取到 `BaseGraphRAG`：

- `index_names()` — 派生 passage/entity/relation 索引名
- `add_texts()` / `add_documents()` — 对外入口，调用 `build_graph()` 后委托 `_bulk_index()`
- `build_graph()` — 三元组抽取、实体/关系/篇章图构建（已有代码，直接抽取）
- `delete_graph()` — 删除三个索引，委托 `_delete_indexes_internal()`
- `delete_documents()` — 按 passage id 级联删除，委托 `_search_by_terms()`、`_delete_or_detach_by_passage_ids()`、`_detach_relation_ids_from_entities()`
- `delete_by_query()` — 先检索再删除
- 所有 `_build_entity_docs()` / `_build_relation_docs()` / `_build_passage_docs()`
- 所有三元组相关：`_get_document_triplets()`、`_extract_triplets()`、`_extract_query_entities()`、`_parse_triplets()`
- 工具方法：`_get_entity_id()`、`_stable_id()`、`_normalize()`、`_simple_extract_entities()`

### 抽象方法

```python
class BaseGraphRAG(ABC):
    @abstractmethod
    def _bulk_index(self, index_name: str, docs: list[dict]) -> None: ...

    @abstractmethod
    def _delete_indexes_internal(self, index_name: str) -> None: ...

    @abstractmethod
    def _delete_docs_internal(self, index_name: str, doc_ids: list[str]) -> int: ...

    @abstractmethod
    def _search_by_terms(
        self, index_name: str, field: str, values: list[str], size: int
    ) -> list[dict]: ...

    @abstractmethod
    def _delete_or_detach_by_passage_ids(
        self, index_name: str, docs: list[dict], deleted_passage_ids: list[str]
    ) -> tuple[list[str], list[str]]: ...

    @abstractmethod
    def _detach_relation_ids_from_entities(self, relation_ids: list[str]) -> None: ...

    @abstractmethod
    def retrieve(
        self, query: str, k: int = 6, entity_top_k: int = 5,
        relation_top_k: int = 8, expansion_degree: int = 1,
        relation_limit: int = 30, return_debug: bool = False,
    ) -> list[dict] | dict: ...
```

## ElasticGraphRAG 变更

保持当前 `ElasticGraphRAG` 类，继承 `BaseGraphRAG`，之前的方法基本不变。
`retrieve()` 仍调用 `ElasticsearchVectorStore.vector_graph_retrieve()`，这是 ES 的优化路径。

## PgGraphRAG 新增

### 索引结构（同一张分区表，靠 `index_name` 区分）

PG 中不创建独立索引，而是在 `PgVectorStore` 的同一张分区表中通过 `index_name` 区分三种文档类型：

- `{prefix}_passages` — passage 文档
- `{prefix}_entities` — entity 文档
- `{prefix}_relations` — relation 文档

### retrieve() 图遍历算法

使用 `AbstractVectorStore` 的公共接口实现多跳图遍历：

```
1. 种子实体检索
   vector_store.vector_search(query, k=entity_top_k, index_name=entity_index)
   → 得到 seed_entity_ids

2. 种子关系检索
   vector_store.vector_search(query, k=relation_top_k, index_name=relation_index)
   → 得到 seed_relation_ids

3. 多跳扩展（degree 次）
   每轮：
     a) 从 entity_ids 找相邻关系（搜索 relation 索引中 metadata.entity_ids 包含任一 entity_id 的行）
     b) 从 relation_ids 找相邻实体（搜索 entity 索引中 metadata.relation_ids 包含任一 relation_id 的行）
   实现方式：对每批 ID，用 vector_store.vector_search 或 search 加 filter_conditions

4. 关系向量裁剪
   kept_relations = []
   for rel_id in expanded_relation_ids:
       rel = vector_store.get(rel_id, index_name=relation_index)
       if rel:
           # 用关系文本做向量相似度重排
           kept_relations.append(...)
   或批量用 vector_search 过滤 ID 列表

5. 最终 passage 召回
   用 kept_relation_ids + expanded_entity_ids 做 filter
   vector_store.vector_search(query, k=k, index_name=passage_index,
       filter_conditions={"metadata.relation_ids": [...], "metadata.entity_ids": [...]})
   → 得到 passages

6. 回退
   如果 passages 为空，回退到 vector_store.retrieve(query, k=k, index_name=passage_index)
```

### AbstractVectorStore 扩展

为了让 PG 的 `vector_search` 支持过滤，需要：

1. 在 `AbstractVectorStore.vector_search()` 签名中增加 `filter_conditions` 参数
2. 在 `PgVectorStore.vector_search()` 中实现 metadata 数组包含过滤（`metadata->'entity_ids' @> '["id"]'::jsonb`）
3. `ElasticsearchVectorStore.vector_search()` 兼容新的 `filter_conditions` 参数

### _bulk_index() 实现

```python
def _bulk_index(self, index_name: str, docs: list[dict]):
    """用 PgVectorStore.add_batch() 批量写入"""
    self.vector_store.add_batch(docs, index_name=index_name)
```

### CRUD 操作

| 操作 | ES 实现 | PG 实现 |
|------|---------|---------|
| `_delete_indexes_internal` | `es_client.indices.delete()` | `DROP TABLE IF EXISTS partition` 或逐行删除 |
| `_delete_docs_internal` | ES bulk delete | `vector_store.delete_batch()` |
| `_search_by_terms` | ES terms query | `SELECT ... WHERE id IN (...)` |
| `_delete_or_detach_by_passage_ids` | ES update/delete | SQL UPDATE/DELETE |
| `_detach_relation_ids_from_entities` | ES update | SQL UPDATE |

## 工厂函数

新增 `create_graph_rag()` 函数，通过 `settings.VECTOR_STORE_BACKEND` 自动返回对应的 GraphRAG 实例：

```python
def create_graph_rag(
    vector_store: AbstractVectorStore,
    graph_name: str,
    chat_model=None,
) -> BaseGraphRAG:
    if isinstance(vector_store, ElasticsearchVectorStore):
        return ElasticGraphRAG(vector_store, graph_name, chat_model)
    elif isinstance(vector_store, PgVectorStore):
        return PgGraphRAG(vector_store, graph_name, chat_model)
    raise ValueError(f"不支持的向量库类型: {type(vector_store)}")
```

## 向后兼容

- `ElasticGraphRAG` 保持 `es` 属性引用和 `__init__` 签名不变
- `BaseGraphRAG` 仅提取逻辑，不改变既有 `ElasticGraphRAG` 的对外行为
- 新增 `PgGraphRAG` 导出自 `deepclaw/common/pg_graph_rag.py`

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `deepclaw/common/vector_store/base.py` | 修改 | `vector_search()` 增加 `filter_conditions` 参数 |
| `deepclaw/common/vector_store/pgsql.py` | 修改 | 实现带 filter 的 `vector_search()` |
| `deepclaw/common/vector_store/elasticsearch.py` | 修改 | 兼容新 `filter_conditions` 参数 |
| `deepclaw/common/elastic_graph_rag.py` | 重构 | 抽取 `BaseGraphRAG`，保持 `ElasticGraphRAG` |
| `deepclaw/common/pg_graph_rag.py` | 新增 | `PgGraphRAG` 实现 |
| `deepclaw/common/__init__.py` | 修改 | 导出 `create_graph_rag` |
| 后续更新 `AGENTS.md` | 修改 | 记录新文件 |
