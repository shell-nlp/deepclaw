# 向量数据库抽象与 PgSQL 实现设计

**日期：** 2026-06-25

**目标：** 把原先散落在 Elasticsearch 实现中的“通用向量库能力”抽成稳定接口，并新增一个基于 PostgreSQL + pgvector + Full Text Search 的实现；同时让普通检索链路优先依赖抽象层，保证后续切换底层向量库时不需要大改业务代码。

## 1. 背景与问题

当前 `deepclaw/common/elastic_utils.py` 中的 `Elasticsearch` 类同时承载了三类职责：

- 通用文档存取：`add`、`add_batch`、`update`、`delete`、`get`、`exists`、`count`
- 通用检索能力：`vector_search`、`keyword_search`、`retrieve`、`search`
- Elasticsearch 专属图扩展：`vector_graph_retrieve` 及其一组图关系辅助方法

这种设计短期内实现直接，但已经暴露出三个问题：

1. 上层代码把“通用向量库能力”和“ES 专属能力”耦合到了同一个具体类上，后续接入其他向量数据库时很难复用。
2. `ElasticGraphRAG` 直接依赖当前 `Elasticsearch` 类，导致“普通 RAG 检索”和“图增强检索”的边界不清晰。
3. 如果直接照搬 ES 类去实现 PostgreSQL 版本，接口会被 ES 的 DSL、索引模型和图扩展细节污染，难以成为长期稳定抽象。

## 2. 设计目标

- 把“通用向量库能力”抽成稳定、可复用的抽象基类。
- Elasticsearch 继续作为一个具体实现存在，并保持现有上层调用尽量不变。
- 新增 `PgVectorStore`，支持：
  - 向量检索
  - 关键词检索（BM25 对应语义）
  - 基础 CRUD
  - 通用 `retrieve` 混合召回
- 支持单个与多个 `index_name` 的联查能力，并保持 ES 与 PG 两种实现的语义可对齐。
- 明确把 graph-RAG 扩展留在 Elasticsearch 实现侧，不污染抽象层。
- 为后续接入其他向量数据库（如 Milvus、Qdrant、Weaviate）预留稳定接口。

## 3. 不做的事

- 不在本次设计中把 `vector_graph_retrieve` 纳入通用抽象。
- 不在本次设计中改写 `ElasticGraphRAG` 的整体图构建流程和图检索语义。
- 不引入新的复杂插件系统或动态加载框架。
- 不要求一次性替换全仓所有 `Elasticsearch` 调用点。
- 不在第一版 PgSQL 实现中引入复杂 rerank、学习排序或多路融合打分。

## 4. 方案对比与结论

### 方案 A：把通用能力和 graph-RAG 一起抽象

优点：

- 看起来“接口更完整”
- 未来图检索似乎也能走统一入口

缺点：

- 抽象会被 ES 专属图能力反向污染
- PostgreSQL 第一版很难做到真实对齐，只能做名义兼容
- 上层接口会变脏，后续接更多向量库成本更高

### 方案 B：只抽象通用向量库能力，ES 图扩展保留为实现专属能力

优点：

- 抽象边界干净，长期更稳
- PostgreSQL 可以快速落地并保持语义一致
- 普通 RAG 可统一，多数据库替换成本低

缺点：

- 图增强检索暂时仍然是 ES 专属能力
- 未来若要统一 graph-RAG，需要另起一层抽象

### 结论

采用 **方案 B**：

- 抽象层只覆盖通用向量库能力
- `vector_graph_retrieve` 继续保留在 Elasticsearch 实现中
- `ElasticGraphRAG` 继续走 ES 实现，但依赖更清晰的 ES store，而不是未来所有向量库都必须实现的基类方法

## 5. 目标结构

目标结构如下：

```text
deepclaw/common/
├── __init__.py
├── elastic_graph_rag.py
└── vector_store/
    ├── __init__.py
    ├── base.py
    ├── elasticsearch.py
    ├── factory.py
    └── pgsql.py
```

### 文件职责

- `deepclaw/common/vector_store/base.py`
  定义 `AbstractVectorStore`，只暴露通用能力。

- `deepclaw/common/vector_store/elasticsearch.py`
  定义 `ElasticsearchVectorStore`，承接当前 ES 的通用向量库能力，并保留 ES 专属扩展方法。

- `deepclaw/common/vector_store/pgsql.py`
  定义 `PgVectorStore`，实现 PostgreSQL + pgvector + FTS 的通用能力。

- `deepclaw/common/vector_store/factory.py`
  提供统一的 `create_vector_store()` 创建入口，让普通检索链路不直接依赖具体实现类。

- `deepclaw/common/elastic_graph_rag.py`
  继续依赖 ES 实现，保留 `vector_graph_retrieve` 的调用语义。

## 6. 抽象接口设计

### 6.1 抽象边界

`AbstractVectorStore` 只定义调用方真正需要依赖的最小公共面，不暴露：

- Elasticsearch DSL
- PostgreSQL SQL 细节
- 图检索扩展能力
- 底层索引创建语法

### 6.2 统一方法

建议统一以下方法：

- `add(content, metadata=None, doc_id=None, index_name=None) -> str`
- `add_batch(documents, index_name=None) -> list[str]`
- `update(doc_id, content=None, metadata=None, index_name=None) -> bool`
- `delete(doc_id, index_name=None) -> bool`
- `delete_batch(doc_ids, index_name=None) -> list[bool]`
- `get(doc_id, index_name=None) -> dict | None`
- `exists(doc_id, index_name=None) -> bool`
- `count(filter_conditions=None, index_name=None, index_names=None) -> int`
- `search(query=None, k=3, filter_conditions=None, index_name=None, index_names=None) -> list[dict]`
- `vector_search(query, k=3, index_name=None, index_names=None, min_similarity=None) -> list[dict]`
- `keyword_search(query, k=3, index_name=None, index_names=None) -> list[dict]`
- `retrieve(query, k=3, index_name=None, index_names=None) -> list[dict]`

约束如下：

- 写入类方法（`add`、`add_batch`、`update`、`delete`）仍然只接受单个 `index_name`
- 读取与检索类方法允许：
  - 只传 `index_name`
  - 只传 `index_names`
  - 两者都不传（表示全部逻辑索引）
- 若同时传入 `index_name` 和 `index_names`，实现应抛出参数冲突错误，避免歧义

这样可以兼容当前单索引调用方式，同时把“多 index 联查”提升为明确契约，而不是以后再补的特例能力。

### 6.3 返回结构

所有实现统一返回与现有代码兼容的文档结构：

- `content`: 文本内容
- `metadata`: 元数据
- `score`: 检索分数（有则返回）
- `id`: 文档标识（实现可返回，但上层不强依赖）

### 6.4 `retrieve` 语义

`retrieve` 继续作为默认混合召回入口：

1. 执行向量检索
2. 执行关键词检索
3. 以 `content` 去重后顺序合并
4. 返回前 `k` 条

第一版保持与当前 ES 逻辑尽量一致，不引入复杂融合打分，优先保证兼容性与可替换性。

当传入多个 `index_name` 时：

- ES 实现可直接利用多索引查询能力
- PG 实现需要在语义上返回“多个逻辑索引联合检索后的 top-k 结果”
- 联查结果仍然遵循同一套去重与截断规则

## 7. Elasticsearch 实现设计

### 7.1 通用能力迁移

把当前 `deepclaw/common/elastic_utils.py` 中以下方法收敛到 `ElasticsearchVectorStore`：

- `add`
- `add_batch`
- `update`
- `delete`
- `delete_batch`
- `get`
- `search`
- `exists`
- `count`
- `vector_search`
- `keyword_search`
- `retrieve`

### 7.2 ES 专属能力保留

以下能力不进入基类，只保留在 ES 实现中：

- `vector_graph_retrieve`
- `_search_graph_items`
- `_vector_search_raw`
- `_expand_es_graph`
- `_relations_by_entities`
- `_entities_by_relations`
- `_evict_relations_by_vector`
- `_search_passages_by_graph`
- `_get_docs_by_ids`
- `_search_by_terms`
- `_hit_to_result`
- `_ids_from_hits`
- `_metadata_list`
- `_simple_extract_entities`

这样做的原因是：

- 这些方法依赖 ES 的索引模型和查询语义
- 它们服务于 graph-RAG，而不是所有向量库的公共需求
- 未来如果要统一 graph-RAG，应单独抽象图检索层，而不是污染向量库基类

### 7.3 业务侧依赖策略

为保证后续切换到 `PgVectorStore` 时业务代码不需要大改，消费方分两类处理：

- 普通检索链路（如 `retrieve()`、`vector_search()`、`keyword_search()`）统一依赖 `AbstractVectorStore`，实例创建集中走 `create_vector_store()`。
- ES 专属能力（如 `ElasticGraphRAG`、当前知识库元数据索引维护）允许继续显式依赖 `ElasticsearchVectorStore`。

这样后续如果普通 RAG 由 ES 切到 PG，主要变更点只会收敛在工厂配置与少量 ES 专属路径，而不是扩散到所有消费方。

## 8. PgSQL 实现设计

### 8.1 技术选型

`PgVectorStore` 基于以下能力实现：

- PostgreSQL
- `pgvector` 扩展：负责向量存储与 ANN 检索
- PostgreSQL Full Text Search：负责关键词检索

对应关系如下：

- ES `knn` -> pgvector 相似度检索
- ES `multi_match` -> PostgreSQL FTS
- ES `retrieve` 混合召回 -> PG 向量检索 + FTS 合并去重

### 8.2 `index_name` 的存储策略

本次不采用“所有 `index_name` 直接混放到一个未分区大表”的方案。

原因如下：

1. 向量检索对物理隔离更敏感。如果所有知识库共用一个 ANN 索引，再用 `WHERE index_name = ...` 过滤，容易出现候选集被其他数据污染，影响召回质量和性能。
2. FTS 对混表更耐受，但随着数据量增长，`search_vector` 的统计与排序成本也会持续上升。
3. 复杂过滤如果再叠加 `jsonb metadata` 查询，执行计划更容易不稳定。

因此采用 **统一接口 + 按 `index_name` 分区** 的方案：

- 抽象层继续保留 `index_name` / `index_names` 参数
- `PgVectorStore` 底层使用统一逻辑模型
- 物理存储上按 `index_name` 做分区隔离

### 8.3 推荐表模型

建议使用一个分区主表，例如逻辑上命名为 `vector_store_documents`，字段包括：

- `id text primary key`
- `index_name text not null`
- `content text not null`
- `metadata jsonb not null default '{}'::jsonb`
- `embedding vector(<dims>) not null`
- `search_vector tsvector not null`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

主表按 `index_name` 做 `LIST PARTITION`，每个分区单独对应一个知识库逻辑索引。

### 8.4 索引设计

每个分区建议具备：

- `btree(id)`
- `btree(index_name)`（分区表中可简化，但保留逻辑说明）
- `GIN(search_vector)`
- `pgvector` ANN 索引：
  - 优先 `hnsw`，若环境受限则 `ivfflat`
- 常用过滤字段如需高频查询，可在后续提升为显式列并建立索引

### 8.5 向量检索策略

`vector_search` 的行为如下：

1. 使用 `embedding_model.embed_query(query)` 生成查询向量
2. 在目标 `index_name` 分区内，或多个目标分区集合上执行向量检索
3. 返回前 `k` 条结果
4. 将距离转换成统一 `score` 字段
5. 支持 `min_similarity` 阈值裁剪

第一版不追求 ES 分数和 PG 分数绝对对齐，只要求：

- 同一实现内部排序稳定
- `score` 可比较
- 上层调用在语义上保持“分数越高越相似”

当传入多个 `index_name` 时，PG 实现不建议简单依赖“跨所有分区直接一次 ANN 查询”作为唯一策略，而建议采用更可控的联查方案：

1. 每个目标分区先各自召回 top-k 或 top-n 候选
2. 在 SQL 层或应用层按统一距离分数归并
3. 再截断到最终 top-k

这样做的原因是：

- 更贴近 ES 多索引联查的语义
- 比未约束的跨分区全局 ANN 查询更稳定
- 更容易控制不同分区数据规模差异带来的召回偏移

### 8.6 关键词检索策略

`keyword_search` 使用 PostgreSQL FTS 实现，建议采用：

- `to_tsvector('simple', content)`
- 配合 `websearch_to_tsquery('simple', :query)` 或 `plainto_tsquery`
- 使用 `ts_rank_cd` 排序

这不是严格数学意义上的 BM25，但在应用语义上可作为“关键词检索”能力对齐，并满足本次“支持 bm25（关键字检索）检索”的目标。

如后续确需更接近 BM25 的行为，可在 PostgreSQL 层进一步增强，但不作为本次第一版目标。

当传入多个 `index_name` 时：

- 直接对多个目标分区联合执行 FTS
- 保持统一排序与 top-k 截断
- 这一路径在 PG 中通常比多分区向量联查更直接

### 8.7 搜索与过滤策略

`search(query=None, filter_conditions=None, index_name=None, index_names=None)` 的语义保持与现有 ES 版本一致：

- 有 `query` 时，执行关键词检索
- 有 `filter_conditions` 时，叠加精确过滤
- 两者都没有时，返回分区内前 `k` 条文档

第一版过滤策略约束如下：

- 对顶层已知简单字段做精确匹配
- 对 `metadata` 中的简单 key/value 允许做等值匹配
- 不在第一版中承诺复杂嵌套 JSON 查询、范围过滤、全文与 JSON 复合优化

这样可以先保证兼容与可实现性，避免把通用抽象做成对 PG 过度承诺的接口。

## 9. 上层兼容策略

### 9.1 现有导出

`deepclaw/common/__init__.py` 现状对外导出：

- `ElasticGraphRAG`
- `Elasticsearch`

本次改造后，建议保持这个导出不失效，并新增可选导出：

- `AbstractVectorStore`
- `ElasticsearchVectorStore`
- `PgVectorStore`

### 9.2 调用方兼容

现有调用路径中，以下方向优先保持兼容：

- `deepclaw/common/elastic_graph_rag.py`
- `deepclaw/middleware/rag.py`
- `deepclaw/tools/retriever.py`
- `deepclaw/web_backend/knowledge_bases/service.py`

兼容原则：

- 现有 ES 路径继续可工作
- 通用检索行为不因抽象层引入而改变
- graph-RAG 行为不因 PG 支持而被迫弱化

### 9.3 构造入口

本次可以先不强行全仓切换到工厂模式，但建议预留统一构造思路，例如未来按配置选择：

- `elasticsearch`
- `pgsql`

第一版重点是把类与边界落稳，不要求同步改造所有实例化入口。

同时，现有上层如果已有单 `index_name` 调用，不要求在本次重构中全部改成 `index_names`；但新接口应从一开始就把多索引联查作为正式能力保留。

## 10. 实施顺序

建议按以下顺序落地：

1. 新建 `deepclaw/common/vector_store/base.py`，定义 `AbstractVectorStore`
2. 新建 `deepclaw/common/vector_store/elasticsearch.py`，迁移 ES 通用能力
3. 保留 ES 专属图检索方法在 ES 实现中
4. 调整 `deepclaw/common/elastic_utils.py` 为兼容层
5. 新建 `deepclaw/common/vector_store/pgsql.py`
6. 调整必要导出与最小调用点
7. 更新 `AGENTS.md`
8. 执行验证与 `codegraph index --force`

## 11. 风险与控制

### 风险 1：兼容层处理不当导致现有 ES 路径回归

控制方式：

- `elastic_utils.py` 先保留原类名与主要调用入口
- 在迁移时优先复用现有逻辑，避免顺手重写
- 对 `retrieve`、`vector_search`、`search` 的行为做回归验证

### 风险 2：把 ES 图扩展错误地下沉到抽象层

控制方式：

- 基类明确只保留通用能力
- `vector_graph_retrieve` 只出现在 ES 实现中
- `ElasticGraphRAG` 继续绑定 ES store，而不是依赖所有向量库

### 风险 3：PgSQL 混表导致召回质量与性能不稳定

控制方式：

- 不采用未分区混表方案
- 按 `index_name` 做物理分区
- 每个分区单独建立向量索引与 FTS 索引

### 风险 4：过滤能力承诺过多，第一版难以稳定实现

控制方式：

- 第一版只承诺简单等值过滤
- 复杂 JSON 过滤不进入公共契约
- 高频过滤字段后续再按需提升为显式列

## 12. 测试与验证要求

至少覆盖以下验证：

- Python 语法检查：
  - `uv run python -m py_compile <changed_file.py>`

- 代码规范检查：
  - `uv run ruff check .`

- 与向量库抽象相关的测试：
  - `uv run pytest tests -q`

- 代码结构更新后，必须执行：
  - `codegraph index --force`

建议补充的测试重点：

- 基类语义测试：
  - `retrieve` 的向量结果与关键词结果合并去重规则

- ES 行为回归测试：
  - `vector_search`
  - `keyword_search`
  - `search`

- PG 行为测试：
  - 结果映射
  - 简单过滤
  - 向量检索与关键词检索的基本契约

## 13. 成功标准

满足以下条件，视为本次设计完成并可进入实现：

- 已存在稳定的 `AbstractVectorStore`
- Elasticsearch 被收敛为一个具体实现，而不是唯一入口
- PgSQL 实现具备向量检索、关键词检索和基础 CRUD 能力
- ES 与 PgSQL 实现都支持多 `index_name` 联查
- `vector_graph_retrieve` 没有被错误塞进基类
- `index_name` 在 PgSQL 中采用分区隔离，而不是未分区混表
- 现有 ES 路径可继续工作
- `AGENTS.md` 已与真实结构保持同步

## 14. 实施原则

- 抽象层只做真正的公共部分，不为单一后端扩展背书。
- 先保兼容，再逐步引导上层迁移到新入口。
- 第一版优先保证行为稳定和接口清晰，不追求高级检索特性一步到位。
- PostgreSQL 实现优先保证“可用且可扩展”，避免为了短期省事选择后续难以维护的混表方案。
