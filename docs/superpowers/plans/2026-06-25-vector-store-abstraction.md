# Vector Store Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `deepclaw/common/elastic_utils.py` 中的通用向量库能力抽成稳定抽象，保留 Elasticsearch 兼容入口，并新增一个支持多 `index_name` 联查的 `PgVectorStore` 实现。

**Architecture:** 新增 `deepclaw/common/vector_store/` 目录，里面定义 `AbstractVectorStore`、`ElasticsearchVectorStore`、`PgVectorStore`。`elastic_utils.py` 退化为 ES 兼容层，继续导出 `Elasticsearch` 名称和 ES 专属图检索方法。PgSQL 版本使用 PostgreSQL + pgvector + Full Text Search，并在物理存储上按 `index_name` 分区，同时在接口上支持单索引和多索引联查。

**Tech Stack:** Python 3.12, Elasticsearch 8.x client, PostgreSQL, pgvector, psycopg, pytest, Ruff, CodeGraph.

**Constraints:** 不执行 `git add`、`git commit`、`git amend`。测试统一使用 `pytest`。Python 改动后至少执行 `py_compile`、`ruff check`，并在完成后执行 `codegraph index --force`。文档与代码注释统一使用中文。读取/检索方法要支持 `index_name` 和 `index_names`，但写入方法仍然只允许单个 `index_name`。

---

### Task 1: 先把抽象层与 ES 多索引语义写成失败测试

**Files:**
- Create: `tests/test_vector_store_base.py`
- Create: `tests/test_vector_store_elasticsearch.py`

- [ ] **Step 1: 新建基类测试，锁定 `index_name` / `index_names` 规范化与冲突行为**

在 `tests/test_vector_store_base.py` 中先定义一个最小 fake store，直接继承计划中的 `AbstractVectorStore`，只实现空方法，专门测试公共辅助逻辑。先把这些行为写死：

```python
import pytest

from deepclaw.common.vector_store.base import AbstractVectorStore


class DummyStore(AbstractVectorStore):
    def add(self, content, metadata=None, doc_id=None, index_name=None):
        raise NotImplementedError

    def add_batch(self, documents, index_name=None):
        raise NotImplementedError

    def update(self, doc_id, content=None, metadata=None, index_name=None):
        raise NotImplementedError

    def delete(self, doc_id, index_name=None):
        raise NotImplementedError

    def delete_batch(self, doc_ids, index_name=None):
        raise NotImplementedError

    def get(self, doc_id, index_name=None):
        raise NotImplementedError

    def exists(self, doc_id, index_name=None):
        raise NotImplementedError

    def count(self, filter_conditions=None, index_name=None, index_names=None):
        raise NotImplementedError

    def search(self, query=None, k=3, filter_conditions=None, index_name=None, index_names=None):
        raise NotImplementedError

    def vector_search(self, query, k=3, index_name=None, index_names=None, min_similarity=None):
        raise NotImplementedError

    def keyword_search(self, query, k=3, index_name=None, index_names=None):
        raise NotImplementedError
```

把下面三类断言一并写进去：

```python
def test_resolve_index_names_accepts_single_name():
    store = DummyStore()
    assert store.resolve_index_names(index_name="kb_demo") == ["kb_demo"]


def test_resolve_index_names_accepts_multiple_names_and_deduplicates():
    store = DummyStore()
    assert store.resolve_index_names(index_names=["kb_a", "kb_b", "kb_a"]) == ["kb_a", "kb_b"]


def test_resolve_index_names_rejects_conflicting_arguments():
    store = DummyStore()
    with pytest.raises(ValueError, match="index_name and index_names"):
        store.resolve_index_names(index_name="kb_a", index_names=["kb_b"])
```

- [ ] **Step 2: 在同一个测试文件里写 `retrieve` 公共去重语义测试**

基类应提供一个公共合并辅助方法，先把测试写出来，明确“向量结果优先、按 `content` 去重、最后截断”的行为：

```python
def test_merge_results_prefers_vector_hits_and_deduplicates_by_content():
    store = DummyStore()
    merged = store.merge_results(
        vector_results=[
            {"content": "alpha", "metadata": {"source": "vector"}, "score": 0.92},
            {"content": "beta", "metadata": {"source": "vector"}, "score": 0.88},
        ],
        keyword_results=[
            {"content": "beta", "metadata": {"source": "keyword"}, "score": 0.77},
            {"content": "gamma", "metadata": {"source": "keyword"}, "score": 0.73},
        ],
        k=3,
    )

    assert [item["content"] for item in merged] == ["alpha", "beta", "gamma"]
    assert merged[1]["metadata"]["source"] == "vector"
```

- [ ] **Step 3: 新建 ES 测试，锁定多索引联查参数和兼容 `retrieve` 行为**

在 `tests/test_vector_store_elasticsearch.py` 中构造 fake embedding model 和 fake ES client，先把这些断言写出来：

```python
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


class FakeESClient:
    def __init__(self):
        self.search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {
            "hits": {
                "hits": [
                    {"_id": "1", "_score": 0.91, "_source": {"content": "alpha", "metadata": {"id": "1"}}},
                    {"_id": "2", "_score": 0.82, "_source": {"content": "beta", "metadata": {"id": "2"}}},
                ]
            }
        }
```

先覆盖两个核心行为：

```python
def test_vector_search_forwards_multiple_index_names():
    store = ElasticsearchVectorStore(
        url="http://localhost:9200",
        embedding_model=FakeEmbeddingModel(),
    )
    store._es_client = FakeESClient()

    store.vector_search(query="hello", k=2, index_names=["kb_a", "kb_b"])

    assert store.es_client.search_calls[0]["index"] == ["kb_a", "kb_b"]


def test_retrieve_merges_vector_and_keyword_hits_without_duplicates(monkeypatch):
    store = ElasticsearchVectorStore(
        url="http://localhost:9200",
        embedding_model=FakeEmbeddingModel(),
    )

    monkeypatch.setattr(
        store,
        "vector_search",
        lambda *args, **kwargs: [
            {"content": "alpha", "metadata": {"source": "vector"}, "score": 0.9},
            {"content": "beta", "metadata": {"source": "vector"}, "score": 0.8},
        ],
    )
    monkeypatch.setattr(
        store,
        "keyword_search",
        lambda *args, **kwargs: [
            {"content": "beta", "metadata": {"source": "keyword"}, "score": 0.7},
            {"content": "gamma", "metadata": {"source": "keyword"}, "score": 0.6},
        ],
    )

    results = store.retrieve(query="hello", k=3, index_names=["kb_a", "kb_b"])
    assert [item["content"] for item in results] == ["alpha", "beta", "gamma"]
```

- [ ] **Step 4: 运行基类和 ES 测试，确认因为新模块不存在而红灯**

Run:

```bash
uv run pytest tests/test_vector_store_base.py tests/test_vector_store_elasticsearch.py -q
```

Expected: FAIL，失败原因应集中在 `deepclaw.common.vector_store` 模块尚未创建，或基类/ES store 中的方法尚未实现，而不是测试文件本身语法错误。

### Task 2: 落地抽象基类与 Elasticsearch 实现，并保留 `elastic_utils.py` 兼容入口

**Files:**
- Create: `deepclaw/common/vector_store/__init__.py`
- Create: `deepclaw/common/vector_store/base.py`
- Create: `deepclaw/common/vector_store/elasticsearch.py`
- Modify: `deepclaw/common/elastic_utils.py`
- Modify: `deepclaw/common/__init__.py`

- [ ] **Step 1: 新建 `base.py`，先实现索引参数规范化和结果合并公共逻辑**

在 `deepclaw/common/vector_store/base.py` 里定义抽象基类，公共逻辑至少包括：

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractVectorStore(ABC):
    """通用向量数据库抽象基类。"""

    def resolve_index_names(
        self,
        *,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[str] | None:
        if index_name and index_names:
            raise ValueError("index_name and index_names cannot be provided together")
        if index_name:
            return [index_name]
        if index_names is None:
            return None
        normalized = [name.strip() for name in index_names if name and name.strip()]
        unique_names = list(dict.fromkeys(normalized))
        if not unique_names:
            raise ValueError("index_names cannot be empty")
        return unique_names

    def merge_results(
        self,
        *,
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        k: int,
    ) -> list[dict[str, Any]]:
        seen_contents: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in vector_results + keyword_results:
            content = item.get("content", "")
            if content in seen_contents:
                continue
            seen_contents.add(content)
            merged.append(item)
            if len(merged) >= k:
                break
        return merged
```

然后把抽象方法签名一次性补齐，确保后续 ES/PG 实现共享同一接口。

- [ ] **Step 2: 新建 `elasticsearch.py`，把现有 ES 通用能力迁到新类，并补齐多索引联查**

在 `deepclaw/common/vector_store/elasticsearch.py` 中建立 `ElasticsearchVectorStore`，优先沿用当前 `deepclaw/common/elastic_utils.py` 的实现，避免顺手重写。核心变化只做三件事：

1. 继承 `AbstractVectorStore`
2. 所有读取/检索方法支持 `index_name` 和 `index_names`
3. `retrieve` 统一走基类 `merge_results`

`vector_search` 的核心形态应接近：

```python
def vector_search(
    self,
    query: str,
    k: int = 3,
    index_name: str | None = None,
    index_names: list[str] | None = None,
    min_similarity: float | None = None,
) -> list[dict[str, Any]]:
    target_indexes = self.resolve_index_names(index_name=index_name, index_names=index_names)
    if not target_indexes:
        raise ValueError("index_name or index_names is required for search operations")

    query_vector = self.embedding_model.embed_query(query)
    results = self.es_client.search(
        index=target_indexes,
        body={
            "query": {
                "knn": {
                    "field": "embedding",
                    "query_vector": query_vector,
                    "num_candidates": max(k * 2, 10),
                }
            }
        },
        size=k,
    )
    return [self._hit_to_result(hit) for hit in results["hits"]["hits"] if min_similarity is None or hit["_score"] >= min_similarity]
```

`keyword_search`、`search`、`count` 同样改成复用 `target_indexes`，其中 `search` 的 `match_all` 路径也要支持多索引。

- [ ] **Step 3: 保留 ES 图检索扩展，并让 `elastic_utils.py` 退化为兼容层**

做法要尽量保守：

1. 把当前 `Elasticsearch` 类整体迁到 `deepclaw/common/vector_store/elasticsearch.py`
2. 保留 `vector_graph_retrieve` 与其辅助私有方法在该新类中
3. 把 `deepclaw/common/elastic_utils.py` 改成兼容导出

兼容层可以直接保持这个形态：

```python
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore


class Elasticsearch(ElasticsearchVectorStore):
    """兼容旧导入路径的 Elasticsearch 向量库实现。"""

    pass
```

这样原来的 `from deepclaw.common.elastic_utils import Elasticsearch` 不需要立刻改。

- [ ] **Step 4: 更新 `__init__.py` 对外导出新类**

把 `deepclaw/common/__init__.py` 调整为：

```python
from deepclaw.common.elastic_graph_rag import ElasticGraphRAG
from deepclaw.common.elastic_utils import Elasticsearch
from deepclaw.common.vector_store import (
    AbstractVectorStore,
    ElasticsearchVectorStore,
    PgVectorStore,
)

__all__ = [
    "AbstractVectorStore",
    "ElasticGraphRAG",
    "Elasticsearch",
    "ElasticsearchVectorStore",
    "PgVectorStore",
]
```

如果此时 `PgVectorStore` 还未实现，可先在 `deepclaw/common/vector_store/__init__.py` 中做延迟导出，避免循环导入。

- [ ] **Step 5: 运行基类和 ES 测试，确认绿灯**

Run:

```bash
uv run pytest tests/test_vector_store_base.py tests/test_vector_store_elasticsearch.py -q
```

Expected: PASS。若失败，优先修 `resolve_index_names()`、`merge_results()` 和 ES 多索引传参，而不是继续推进 PgSQL 实现。

### Task 3: 先写 PgSQL 红灯测试，再实现分区化 `PgVectorStore`

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `deepclaw/common/vector_store/pgsql.py`
- Create: `tests/test_vector_store_pgsql.py`

- [ ] **Step 1: 先把 PgSQL store 的构造和 SQL 语义写成失败测试**

在 `tests/test_vector_store_pgsql.py` 中使用 fake connection / fake cursor，不依赖真实 PostgreSQL 实例，先锁定这四个行为：

1. `index_name` 和 `index_names` 同时传入时报错
2. `_partition_table_name("kb-demo")` 会生成稳定、合法的分区名
3. `keyword_search(..., index_names=["kb_a", "kb_b"])` 会走多分区 FTS
4. `vector_search(..., index_names=["kb_a", "kb_b"])` 会走“分区内先召回，再归并”的路径，而不是把所有逻辑直接退化成单索引查询

测试骨架可以先写成：

```python
import pytest

from deepclaw.common.vector_store.pgsql import PgVectorStore


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None
```

先把这些断言写进测试：

```python
def test_keyword_search_rejects_conflicting_index_arguments():
    store = PgVectorStore(database_url="postgresql://demo", embedding_model=FakeEmbeddingModel(), embedding_dimensions=3)
    with pytest.raises(ValueError, match="index_name and index_names"):
        store.keyword_search("hello", index_name="kb_a", index_names=["kb_b"])


def test_partition_table_name_is_stable():
    store = PgVectorStore(database_url="postgresql://demo", embedding_model=FakeEmbeddingModel(), embedding_dimensions=3)
    assert store._partition_table_name("kb-demo") == "vector_store_documents_kb_demo"
```

- [ ] **Step 2: 运行 PgSQL 测试，确认新模块不存在导致红灯**

Run:

```bash
uv run pytest tests/test_vector_store_pgsql.py -q
```

Expected: FAIL，失败应指向 `deepclaw.common.vector_store.pgsql` 模块尚未创建或关键方法未实现。

- [ ] **Step 3: 通过包管理器添加 `pgvector` 依赖**

直接使用包管理器，不手写版本号：

```bash
uv add pgvector
```

Expected: `pyproject.toml` 与 `uv.lock` 被自动更新，新增 `pgvector` 依赖。

- [ ] **Step 4: 新建 `pgsql.py`，先落 `PgVectorStore` 的基础骨架与连接管理**

`PgVectorStore` 先保持同步接口，构造参数建议如下：

```python
from __future__ import annotations

from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from deepclaw.common.vector_store.base import AbstractVectorStore


class PgVectorStore(AbstractVectorStore):
    """基于 PostgreSQL + pgvector 的向量库实现。"""

    def __init__(
        self,
        database_url: str,
        *,
        embedding_model=None,
        embedding_dimensions: int | None = None,
        table_name: str = "vector_store_documents",
        schema_name: str = "public",
    ):
        self.database_url = database_url
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.table_name = table_name
        self.schema_name = schema_name
```

再补三个内部基础方法：

```python
def _connect(self):
    conn = psycopg.connect(self.database_url, autocommit=True)
    register_vector(conn)
    return conn


def _qualified_table_name(self) -> str:
    return f"{self.schema_name}.{self.table_name}"


def _partition_table_name(self, index_name: str) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in index_name.lower())
    return f"{self.table_name}_{normalized}"
```

同时补 `_require_single_index_name()`，专门给写入类方法使用，避免误写多索引。

- [ ] **Step 5: 实现基础建表、分区创建与写入类方法**

先把最小可用 schema 建起来，不要一开始就做太多扩展。核心 SQL 形态应接近：

```python
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.vector_store_documents (
    id text NOT NULL,
    index_name text NOT NULL,
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(3) NOT NULL,
    search_vector tsvector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_name, id)
) PARTITION BY LIST (index_name);
```

每个 `index_name` 分区创建时，同时建：

```sql
CREATE TABLE IF NOT EXISTS public.vector_store_documents_kb_demo
PARTITION OF public.vector_store_documents
FOR VALUES IN ('kb_demo');

CREATE INDEX IF NOT EXISTS vector_store_documents_kb_demo_search_vector_idx
ON public.vector_store_documents_kb_demo
USING GIN (search_vector);
```

写入 `add()` 时，把 `search_vector` 直接写成：

```python
search_vector_sql = "to_tsvector('simple', %(content)s)"
```

`update()` 时若内容变化，记得同时刷新 `embedding` 与 `search_vector`。

- [ ] **Step 6: 实现查询类方法，先把多索引联查语义做稳**

`keyword_search()` 先实现成最直接的 PG FTS 方案：

```python
SELECT id, content, metadata, ts_rank_cd(search_vector, websearch_to_tsquery('simple', %(query)s)) AS score
FROM public.vector_store_documents
WHERE index_name = ANY(%(index_names)s)
  AND search_vector @@ websearch_to_tsquery('simple', %(query)s)
ORDER BY score DESC
LIMIT %(limit)s
```

`vector_search()` 不要简单只写一个“全局跨分区 ANN 查询”，而要明确按 spec 走两段式联查：

1. 对每个目标 `index_name` 分区取 top-k 或 top-n 候选
2. 把每个分区结果映射成统一文档结构
3. 在 Python 层按 `score` 排序并截断到最终 `k`

核心伪代码应接近：

```python
def vector_search(...):
    target_indexes = self.resolve_index_names(index_name=index_name, index_names=index_names)
    query_vector = self.embedding_model.embed_query(query)
    candidates = []
    for target_index in target_indexes or self.list_index_names():
        rows = self._fetch_vector_candidates(
            index_name=target_index,
            query_vector=query_vector,
            limit=max(k, 8),
        )
        candidates.extend(rows)
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return self._apply_min_similarity(candidates, min_similarity)[:k]
```

`retrieve()` 则直接复用基类：

```python
def retrieve(self, query, k=3, index_name=None, index_names=None):
    vector_results = self.vector_search(query, k, index_name=index_name, index_names=index_names)
    keyword_results = self.keyword_search(query, k, index_name=index_name, index_names=index_names)
    return self.merge_results(vector_results=vector_results, keyword_results=keyword_results, k=k)
```

- [ ] **Step 7: 运行 PgSQL 测试并修到绿灯**

Run:

```bash
uv run pytest tests/test_vector_store_pgsql.py -q
```

Expected: PASS。若失败，优先修参数冲突校验、分区命名和多索引联查路径，不要跳过测试直接做全量验证。

### Task 4: 同步文档与仓库说明，并完成最小验证

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-06-25-vector-store-abstraction-design.md`（仅在实现落地后需要补充少量真实路径差异时修改）

- [ ] **Step 1: 更新 `AGENTS.md` 的代码结构说明**

在 `AGENTS.md` 的“核心能力层”或适合的位置补上 `vector_store` 目录的真实职责，至少说明：

```markdown
- `deepclaw/common/vector_store/`
  向量数据库抽象层，包含通用 `AbstractVectorStore`、Elasticsearch 实现和 PgSQL/pgvector 实现。

- `deepclaw/common/elastic_utils.py`
  现作为 Elasticsearch 向量库的兼容导出层，保留历史导入路径与 ES 图检索扩展能力。
```

不要删除已有 `elastic_graph_rag.py` 的说明，只补充真实结构变化。

- [ ] **Step 2: 对新增/修改的 Python 文件逐个做语法检查**

Run:

```bash
uv run python -m py_compile deepclaw/common/vector_store/base.py
uv run python -m py_compile deepclaw/common/vector_store/elasticsearch.py
uv run python -m py_compile deepclaw/common/vector_store/pgsql.py
uv run python -m py_compile deepclaw/common/elastic_utils.py
```

Expected: 所有命令无输出并退出成功。

- [ ] **Step 3: 跑 Ruff，确认没有引入新的 lint 错误**

Run:

```bash
uv run ruff check .
```

Expected: `All checks passed!`，或至少不出现这次修改引入的新错误。

- [ ] **Step 4: 跑与本次改动直接相关的测试集**

Run:

```bash
uv run pytest tests/test_vector_store_base.py tests/test_vector_store_elasticsearch.py tests/test_vector_store_pgsql.py -q
```

如果这三项已经稳定，再补一轮仓库测试：

```bash
uv run pytest tests -q
```

Expected: 新增测试全部 PASS；若全量测试存在既有失败，记录出来，但不要把它们误判成本次回归。

- [ ] **Step 5: 完成后刷新 CodeGraph 索引**

Run:

```bash
codegraph index --force
```

Expected: 索引完成，无阻塞性错误。

## Self-Review Checklist

- [ ] 抽象层是否只保留通用向量库能力，没有把 `vector_graph_retrieve` 塞进基类？
- [ ] 读取/检索方法是否已经正式支持 `index_name` / `index_names`，且冲突参数会报错？
- [ ] ES 兼容路径 `deepclaw.common.elastic_utils.Elasticsearch` 是否仍可导入？
- [ ] PG 实现是否按 `index_name` 分区，而不是把所有逻辑索引混进未分区大表？
- [ ] PG 多索引向量联查是否走了“各分区先召回、再统一归并”的路径？
- [ ] `AGENTS.md` 是否已同步到真实结构？
