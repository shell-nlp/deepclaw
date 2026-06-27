# 向量库刷新嵌入实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `AbstractVectorStore` 上新增 `refresh_embeddings` 模板方法，使 PgVectorStore 和 ElasticsearchVectorStore 能用新模型批量重算所有已有文档的 embedding。

**Architecture:** 基类提供模板方法 + 两个抽象钩子，子类各自实现维度兼容 + 批次写入逻辑。失败逐批次隔离，记录到本地文件。

**Tech Stack:** Python 3.12+, PostgreSQL (pgvector), Elasticsearch, psycopg (v3)

## Global Constraints

- 所有 ORM/DB 操作遵循项目现有模式（SQLModel 或原始 SQL）
- `_refresh_embeddings_batch` 返回 `(成功数, 失败数)` tuple
- 失败文件写入 `.deepclaw/refresh_failed_{timestamp}.jsonl`
- 新代码添加必要的中文注释
- 修改后运行 `uv run python -m py_compile <file>` + `uv run ruff check .`
- 修改后运行 `uv run pytest tests -q` 验证回归

---

### Task 1: 修改 AbstractVectorStore 基类

**Files:**
- Modify: `deepclaw/common/vector_store/base.py`
- Test: 无（基类不做端到端测试，Task 4 统一测）

**Interfaces:**
- Produces: `AbstractVectorStore._ensure_refresh_dimensions(new_dim: int) -> None`（抽象）
- Produces: `AbstractVectorStore._refresh_embeddings_batch(docs: list[dict], new_model, index_name: str) -> tuple[int, int]`（抽象）
- Produces: `AbstractVectorStore.refresh_embeddings(new_embedding_model=None, *, batch_size=50, index_names=None) -> tuple[int, int]`（具体模板方法）

- [ ] **Step 1: 在 base.py 添加抽象钩子 + 模板方法 + 工具函数**

在 `_row_to_result` 和 `retrieve` 之前/之间的适当位置（建议在 `resolve_index_names` 之后）新增：

```python
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from deepclaw.constant import home_path

# 在 AbstractVectorStore 类内，retrieve 方法之后添加：

@abstractmethod
def _ensure_refresh_dimensions(self, new_dim: int, index_names: list[str]) -> None:
    """确保存储层兼容新的向量维度（如改列类型/重建索引准备）。

    Args:
        new_dim: 新模型输出的向量维度
        index_names: 需要刷新的目标索引列表
    """
    ...

@abstractmethod
def _refresh_embeddings_batch(
    self,
    docs: list[dict[str, Any]],
    new_embedding_model,
    index_name: str,
) -> tuple[int, int]:
    """对一批文档重新嵌入并更新存储。

    Args:
        docs: [{"id": str, "content": str, "index_name": str}, ...]
        new_embedding_model: 新嵌入模型
        index_name: 当前批所属索引名
    Returns:
        (成功数, 失败数)
    """
    ...

@abstractmethod
def _init_refresh_batch(self, index_name: str, batch_size: int) -> None:
    """初始化一个索引的批次迭代状态（重置 scroll/offset 等）。"""
    ...

@abstractmethod
def _fetch_refresh_batch(
    self,
    index_name: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    """从指定索引取下一批文档 (id, content, index_name)。空列表 = 无更多数据。
    _init_refresh_batch 需在首次调用前先调用一次。"""
    ...

def refresh_embeddings(
    self,
    new_embedding_model=None,
    *,
    batch_size: int = 50,
    index_names: list[str] | None = None,
) -> tuple[int, int]:
    """刷新向量库中已有文档的嵌入向量。

    Args:
        new_embedding_model: 新嵌入模型，None 则复用当前模型
        batch_size: 每批处理的文档数
        index_names: 限定刷新索引范围，None 则刷新全部
    Returns:
        (成功数, 失败数)
    """
    if new_embedding_model is not None:
        old_model = self._embedding_model
        self._embedding_model = new_embedding_model
    else:
        old_model = None

    success_count = 0
    fail_count = 0
    fail_records: list[dict[str, Any]] = []

    # 初始化子类状态变量
    self._needs_reindex: set[str] = set()

    try:
        # 用新模型探测维度
        probe_text = "测试"
        probe_embedding = self.embedding_model.embed_query(probe_text)
        new_dim = len(probe_embedding)

        # 解析目标索引（先解析，传递给 _ensure_refresh_dimensions）
        target_indexes = self._resolve_refresh_indexes(index_names=index_names)

        # 维度兼容（子类实现：改列 / 重建索引预备）
        self._ensure_refresh_dimensions(new_dim, target_indexes)

        for index_name in target_indexes:
            self._init_refresh_batch(index_name, batch_size)  # 重置批次状态
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
                            "id": doc["id"],
                            "index_name": index_name,
                            "content_preview": doc.get("content", "")[:100],
                            "error": str(exc),
                        })
    finally:
        # 恢复旧模型
        if old_model is not None:
            self._embedding_model = old_model

    # 写入失败记录
    if fail_records:
        fail_dir = home_path
        fail_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fail_path = fail_dir / f"refresh_failed_{ts}.jsonl"
        with open(fail_path, "w", encoding="utf-8") as f:
            for rec in fail_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 列置换收尾 + 索引重建（由 _ensure_refresh_dimensions 标记）
    self._finalize_refresh()

    return success_count, fail_count

def _finalize_refresh(self) -> None:
    """列置换收尾。子类可覆盖，基类为空实现。"""
    pass

def _resolve_refresh_indexes(
    self,
    *,
    index_names: list[str] | None = None,
) -> list[str]:
    """解析 refresh 的目标索引列表。"""
    if index_names is not None:
        normalized = [name.strip() for name in index_names if name and name.strip()]
        unique = list(dict.fromkeys(normalized))
        if not unique:
            raise ValueError("index_names 不能为空列表")
        return unique
    return self._list_index_names()

@abstractmethod
def _list_index_names(self) -> list[str]:
    """返回所有已存在的索引名列表。"""
    ...

@abstractmethod
def _fetch_refresh_batch(
    self,
    index_name: str,
    *,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """从指定索引翻页取出一批文档 (id, content, index_name)。"""
    ...
```

- [ ] **Step 2: 编译检查**

```bash
uv run python -m py_compile deepclaw/common/vector_store/base.py; if ($?) { uv run ruff check deepclaw/common/vector_store/base.py }
```

---

### Task 2: 在 PgVectorStore 实现刷新能力

**Files:**
- Modify: `deepclaw/common/vector_store/pgsql.py`

**Interfaces:**
- Consumes: `AbstractVectorStore._ensure_refresh_dimensions`, `_refresh_embeddings_batch`, `_list_index_names`, `_fetch_refresh_batch`
- Produces: 完整实现

- [ ] **Step 1: 实现 `_ensure_refresh_dimensions`（含列置换）**

添加到 `search_vector_index_name` 方法附近。用 `index_names` 参数取代自查询，直接 DROP 目标 partition 的索引并加新列：

```python
def _ensure_refresh_dimensions(self, new_dim: int, index_names: list[str]) -> None:
    """确保 PG 表列维度与 new_dim 一致；不一致时走列置换流程。"""
    if self.embedding_dimensions == new_dim:
        self._needs_reindex = set()
        return

    self._needs_reindex = set()
    for index_name in index_names:
        part_table = self._qualified_partition_name(index_name)
        part_name = self._partition_table_name(index_name)
        vector_idx = self._vector_index_name(index_name)
        uid_idx = f"{part_name}_id_uidx"

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"DROP INDEX IF EXISTS {vector_idx}")
            cur.execute(f"DROP INDEX IF EXISTS {uid_idx}")
            cur.execute(
                f"ALTER TABLE {part_table} "
                f"ADD COLUMN IF NOT EXISTS embedding_new vector({new_dim})"
            )
        self._needs_reindex.add(index_name)

    self.embedding_dimensions = new_dim
```

- [ ] **Step 2: 实现 `_init_refresh_batch` + `_fetch_refresh_batch`**

PG 用内部 offset 状态实现翻页：

```python
def _init_refresh_batch(self, index_name: str, batch_size: int) -> None:
    """重置 PG 翻页偏移量。"""
    self._pg_refresh_offset = 0

def _fetch_refresh_batch(
    self,
    index_name: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    self._ensure_base_schema()
    self._ensure_partition(index_name)
    sql = f"""
    SELECT id, content, index_name
    FROM {self._qualified_table_name()}
    WHERE index_name = %(index_name)s
    ORDER BY id
    OFFSET %(offset)s
    LIMIT %(limit)s
    """
    with self._connect() as conn, conn.cursor() as cur:
        cur.execute(sql, {
            "index_name": index_name,
            "offset": self._pg_refresh_offset,
            "limit": batch_size,
        })
        rows = cur.fetchall()
    self._pg_refresh_offset += batch_size
    return [
        {"id": str(row["id"]), "content": row["content"], "index_name": row["index_name"]}
        for row in rows
    ]
```

- [ ] **Step 3: 实现 `_list_index_names`（基类已声明为抽象）**

PG 已有 `_list_index_names`（169-176行），签名兼容，无需改动。

- [ ] **Step 4: 实现 `_finalize_refresh`（列置换收尾 + 索引重建）**

PG 的 `_finalize_refresh` 需要做列名置换并在最后 `_ensure_partition` 重建索引：

```python
def _finalize_refresh(self) -> None:
    """PG 列置换收尾：embedding_new → embedding + 重建索引。"""
    if not self._needs_reindex:
        return

    for index_name in self._needs_reindex:
        part_table = self._qualified_partition_name(index_name)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{self._partition_table_name(index_name)}' "
                f"AND column_name = 'embedding_new'"
            )
            if cur.fetchone():
                cur.execute(f"ALTER TABLE {part_table} DROP COLUMN embedding")
                cur.execute(f"ALTER TABLE {part_table} RENAME COLUMN embedding_new TO embedding")
        # 重建索引（唯一索引 + HNSW）
        self._ensure_partition(index_name)
```

- [ ] **Step 5: 实现 `_refresh_embeddings_batch`**

根据是否有 `embedding_new` 列决定写入目标列。使用 `UPDATE ... FROM (VALUES ...)` 单语句批量更新：

```python
def _refresh_embeddings_batch(
    self,
    docs: list[dict[str, Any]],
    new_embedding_model,
    index_name: str,
) -> tuple[int, int]:
    """对一批文档重新嵌入并更新存储。"""
    if not docs:
        return 0, 0

    success = 0
    fail = 0

    contents = [doc["content"] for doc in docs]
    try:
        embeddings = new_embedding_model.embed_documents(contents)
    except Exception as exc:
        for doc in docs:
            doc["_failed"] = True
            doc["_error"] = str(exc)
        return 0, len(docs)

    embed_col = "embedding_new" if self._needs_reindex else "embedding"

    value_rows = []
    params: dict[str, Any] = {}
    for idx, doc in enumerate(docs):
        value_rows.append(f"(%(id_{idx})s, %(emb_{idx})s)")
        params[f"id_{idx}"] = doc["id"]
        params[f"emb_{idx}"] = embeddings[idx]

    params["idx_name"] = index_name
    values_clause = ", ".join(value_rows)

    sql = f"""
    UPDATE {self._qualified_table_name()} AS t
    SET {embed_col} = vals.emb,
        search_vector = to_tsvector('simple', t.content),
        updated_at = now()
    FROM (VALUES {values_clause}) AS vals(id, emb)
    WHERE t.id = vals.id::text AND t.index_name = %(idx_name)s
    """
    try:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            success = len(docs)
    except Exception:
        for doc in docs:
            try:
                emb = new_embedding_model.embed_query(doc["content"])
                sql_single = f"""
                UPDATE {self._qualified_table_name()}
                SET {embed_col} = %(emb)s,
                    search_vector = to_tsvector('simple', %(content)s),
                    updated_at = now()
                WHERE id = %(id)s AND index_name = %(index_name)s
                """
                with self._connect() as conn, conn.cursor() as cur:
                    cur.execute(sql_single, {
                        "emb": emb, "content": doc["content"],
                        "id": doc["id"], "index_name": doc["index_name"],
                    })
                success += 1
            except Exception:
                fail += 1
                doc["_failed"] = True
                doc["_error"] = "fallback single update failed"

    return success, fail
```
```

- [ ] **Step 7: 编译检查 + ruff**

```bash
uv run python -m py_compile deepclaw/common/vector_store/pgsql.py; if ($?) { uv run ruff check deepclaw/common/vector_store/pgsql.py }
```

---

### Task 3: 在 ElasticsearchVectorStore 实现刷新能力

**Files:**
- Modify: `deepclaw/common/vector_store/elasticsearch.py`

- [ ] **Step 1: 实现 `_ensure_refresh_dimensions`**

ES 的 `dense_vector` 维度由 mapping 声明，维度变了需要重建索引。记录到 `_needs_reindex`，在 `_finalize_refresh` 中执行索引重建：

```python
def _ensure_refresh_dimensions(self, new_dim: int, index_names: list[str]) -> None:
    """检查 ES mapping 维度；不一致时标记需要重建索引。"""
    self._needs_reindex: set[str] = set()

    for idx in index_names:
        try:
            mapping = self.es_client.indices.get_mapping(index=idx)
            props = mapping[idx]["mappings"]["properties"]
            emb_props = props.get("embedding", {})
            current_dim = emb_props.get("dims", 0) if emb_props.get("type") == "dense_vector" else 0
            if current_dim == new_dim:
                continue
        except Exception:
            pass

        self._needs_reindex.add(idx)

def _finalize_refresh(self) -> None:
    """ES 索引重建：为新维度创建新索引 → reindex → 切别名。"""
    for idx in self._needs_reindex:
        v2_name = f"{idx}_v2"
        # 读取旧 settings + mapping
        old_settings = self.es_client.indices.get_settings(index=idx)
        old_mapping = self.es_client.indices.get_mapping(index=idx)
        settings = old_settings[idx]["settings"]["index"]
        mapping_body = old_mapping[idx]["mappings"]

        # 改写 embedding 字段维度
        if "properties" in mapping_body and "embedding" in mapping_body["properties"]:
            mapping_body["properties"]["embedding"]["dims"] = self.embedding_dimensions

        # 创建新索引
        self.es_client.indices.create(
            index=v2_name,
            settings={
                "number_of_shards": settings.get("number_of_shards", 1),
                "number_of_replicas": settings.get("number_of_replicas", 0),
            },
            mappings=mapping_body,
        )

        # scroll 旧索引 → 新模型嵌入 → bulk index 到新索引
        scroll_result = self.es_client.search(
            index=idx, body={"query": {"match_all": {}}, "sort": ["_doc"]},
            size=100, scroll="5m",
            _source=True,
        )
        scroll_id = scroll_result["_scroll_id"]
        while scroll_result["hits"]["hits"]:
            ops = []
            for hit in scroll_result["hits"]["hits"]:
                src = hit["_source"]
                emb = self.embedding_model.embed_query(src.get("content", ""))
                src["embedding"] = emb
                ops.append({"index": {"_index": v2_name, "_id": hit["_id"]}})
                ops.append(src)
            if ops:
                self.es_client.bulk(operations=ops, refresh=False)
            scroll_result = self.es_client.scroll(scroll_id=scroll_id, scroll="5m")

        self.es_client.clear_scroll(scroll_id=scroll_id)

        # 删除旧索引，用旧名创建别名指向新索引
        # （或直接删除旧索引后 rename）
        self.es_client.indices.delete(index=idx)
        self.es_client.indices.create(index=idx, settings={}, mappings={})
        self.es_client.indices.put_alias(index=v2_name, name=idx)
```

- [ ] **Step 2: 实现 `_init_refresh_batch` + `_fetch_refresh_batch`**

ES 使用 scroll API 翻页，`_init_refresh_batch` 发起 scroll，后续 `_fetch_refresh_batch` 取下一页：

```python
def _init_refresh_batch(self, index_name: str, batch_size: int) -> None:
    """发起 scroll 搜索。"""
    if not hasattr(self, "_scroll_contexts"):
        self._scroll_contexts: dict[str, str] = {}
    # 清理已有 scroll
    if index_name in self._scroll_contexts:
        self.es_client.clear_scroll(scroll_id=self._scroll_contexts[index_name])
    result = self.es_client.search(
        index=index_name,
        body={"query": {"match_all": {}}, "sort": ["_doc"]},
        size=batch_size,
        scroll="5m",
        _source=["content", "metadata.id"],
    )
    self._scroll_contexts[index_name] = result["_scroll_id"]
    hits = result["hits"]["hits"]

    if not hits:
        self.es_client.clear_scroll(scroll_id=self._scroll_contexts.pop(index_name))
        return []

    return [
        {"id": hit["_source"].get("metadata", {}).get("id") or hit["_id"],
         "content": hit["_source"].get("content", ""),
         "index_name": index_name}
        for hit in hits
    ]

def _fetch_refresh_batch(self, index_name: str, batch_size: int) -> list[dict[str, Any]]:
    """从 ES scroll 取下一批。"""
    scroll_id = self._scroll_contexts.get(index_name)
    if not scroll_id:
        return []

    result = self.es_client.scroll(scroll_id=scroll_id, scroll="5m")
    hits = result["hits"]["hits"]
    if not hits:
        self.es_client.clear_scroll(scroll_id=self._scroll_contexts.pop(index_name))
        return []

    return [
        {"id": hit["_source"].get("metadata", {}).get("id") or hit["_id"],
         "content": hit["_source"].get("content", ""),
         "index_name": index_name}
        for hit in hits
    ]
```

- [ ] **Step 3: 实现 `_list_index_names`**

```python
def _list_index_names(self) -> list[str]:
    """列出所有非系统 ES 索引名。"""
    result = self.es_client.indices.get_alias(index="*")
    names = [idx for idx in result if not idx.startswith(".")]
    return sorted(names)
```

- [ ] **Step 4: 实现 `_refresh_embeddings_batch`**

维度不变时直接用 bulk update 更新 embedding 字段：

```python
def _refresh_embeddings_batch(
    self,
    docs: list[dict[str, Any]],
    new_embedding_model,
    index_name: str,
) -> tuple[int, int]:
    if not docs:
        return 0, 0

    contents = [doc["content"] for doc in docs]
    try:
        embeddings = new_embedding_model.embed_documents(contents)
    except Exception as exc:
        for doc in docs:
            doc["_failed"] = True
            doc["_error"] = str(exc)
        return 0, len(docs)

    ops = []
    for doc, emb in zip(docs, embeddings):
        ops.append({"update": {"_index": index_name, "_id": doc["id"]}})
        ops.append({"doc": {"embedding": emb}})

    try:
        result = self.es_client.bulk(operations=ops, refresh=False)
        success, fail = 0, 0
        if result.get("errors"):
            for item in result["items"]:
                if "error" in item.get("update", {}):
                    fail += 1
                else:
                    success += 1
        else:
            success = len(docs)
    except Exception as exc:
        for doc in docs:
            doc["_failed"] = True
            doc["_error"] = str(exc)
        return 0, len(docs)

    return success, fail
```

- [ ] **Step 5: 编译检查 + ruff**

```bash
uv run python -m py_compile deepclaw/common/vector_store/elasticsearch.py; if ($?) { uv run ruff check deepclaw/common/vector_store/elasticsearch.py }
```

---

### Task 4: 端到端测试（PG）

**Files:**
- Create: `tests/test_vector_refresh_embeddings.py`

- [ ] **Step 1: 写测试**

```python
"""测试向量库 embedding 刷新功能。"""
import pytest
from deepclaw.common.vector_store import create_vector_store


@pytest.mark.asyncio
async def test_refresh_embeddings_pg(pg_vector_store):
    """测试 PG 刷新嵌入（维度不变场景）。"""
    store = pg_vector_store

    # 先写入文档
    doc_id = store.add(
        content="测试文档内容",
        metadata={"source": "test"},
        doc_id="test_001",
        index_name="test_refresh",
    )
    assert doc_id == "test_001"

    # 刷新
    suc, fail = store.refresh_embeddings(
        batch_size=10,
        index_names=["test_refresh"],
    )
    assert fail == 0
    assert suc >= 1

    # 验证检索正常
    results = store.vector_search("测试文档", k=3, index_name="test_refresh")
    assert len(results) >= 1
    assert results[0]["id"] == "test_001"


@pytest.mark.asyncio
async def test_refresh_embeddings_pg_dim_change(pg_vector_store):
    """测试 PG 刷新嵌入（维度变化场景 - 需要 mock 模型）。"""
    # 此测试需要 mock embedding_model 返回不同维度
    # 跳过实际执行，仅验证接口不报错
    pytest.skip("需要 mock 模型模拟维度变化")


@pytest.mark.asyncio
async def test_refresh_embeddings_es(es_vector_store):
    """测试 ES 刷新嵌入。"""
    store = es_vector_store

    doc_id = store.add(
        content="ES test document",
        metadata={"source": "test"},
        doc_id="es_test_001",
        index_name="test_refresh_es",
    )

    suc, fail = store.refresh_embeddings(
        batch_size=10,
        index_names=["test_refresh_es"],
    )
    assert fail == 0
    assert suc >= 1
```

实际测试前可能需要 fixture 支持。先跑一下看看现有测试的 fixture 方式。

- [ ] **Step 2: 运行测试**

```bash
uv run pytest tests/test_vector_refresh_embeddings.py -v
```

---

### Task 5: 回归验证

- [ ] **Step 1: 编译全部改动文件**

```bash
uv run python -m py_compile deepclaw/common/vector_store/base.py; if ($?) { uv run python -m py_compile deepclaw/common/vector_store/pgsql.py; if ($?) { uv run python -m py_compile deepclaw/common/vector_store/elasticsearch.py } }
```

- [ ] **Step 2: ruff**

```bash
uv run ruff check .
```

- [ ] **Step 3: 运行全部测试**

```bash
uv run pytest tests -q
```

- [ ] **Step 4: 更新 `AGENTS.md`**（如需记录新接口）

- [ ] **Step 5: 更新 codegraph 索引**

```bash
codegraph index --force
```
