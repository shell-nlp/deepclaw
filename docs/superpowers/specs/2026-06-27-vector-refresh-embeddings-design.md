# 向量库刷新嵌入设计文档

## 背景

向量库存储的 embedding 向量维度与值由训练模型决定。当用户更换嵌入模型后：

- 新模型可能输出不同维度的向量（例如 1536d → 1024d）
- 即使维度相同，向量值语义空间也不同
- 已有向量与新模型生成的向量无法在同一检索空间中比较

需要一个统一的刷新机制，用新模型重新嵌入所有已有文档内容并更新存储。

## 设计目标

- 传入新 embedding model，自动刷新全部或指定索引的已有向量
- 支持维度变化场景（PG 列类型变更、ES 索引重建）
- 批量处理，内存可控
- 逐批次提交，失败记录落地，不影响已成功部分
- 返回 `(成功数, 失败数)` 统计

## 接口定义

在 `AbstractVectorStore` 新增抽象方法：

```python
@abstractmethod
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
```

### 设计说明

- 不用 `index_name` + `index_names` 两参数模式，统一为 `index_names: list[str] | None`，调用传单索引用 `["foo"]`
- `None` = 全量刷新，与 `vector_search` 等方法的默认行为一致
- 返回值统一为 `(int, int)` tuple，不抛出汇总异常

## 核心流程（基类骨架层）

基类的 `refresh_embeddings` **不是**抽象方法，而是模板方法（template method），
内部调用两个由子类实现的钩子：

- `_ensure_refresh_dimensions(new_dim: int)` — 确保存储层兼容新维度（改列类型/重建索引）
- `_refresh_embeddings_batch(docs: list[dict], new_model) -> tuple[int, int]` — 处理一批文档

基类 `refresh_embeddings` 负责的公共逻辑：

1. 设置新 embedding model（若传入）
2. 解析目标 index_names（None 时通过 `_list_index_names()` 或等价方法获取全量）
3. 确定新维度：用新模型嵌入一条测试文本
4. 调用 `_ensure_refresh_dimensions(new_dim)` — 子类实现
5. 批次循环（offset/limit 翻页或 scroll 翻页），每批调 `_refresh_embeddings_batch`
6. 失败记录写入 `.deepclaw/refresh_failed_{timestamp}.jsonl`
7. 返回 `(成功数, 失败数)`

### 失败记录格式

路径：`.deepclaw/refresh_failed_{timestamp}.jsonl`

每行 JSON：

```json
{"id": "...", "index_name": "...", "content_preview": "前100字符", "error": "异常消息"}
```

## PgVectorStore 实现

### 维度确定

当前列维度通过 `pg_attribute.atttypmod - 4` 读取（已有 `_ensure_column_dimension` 方法可以复用）。

### 维度不变场景

```
for each index_name in target_indexes:
    offset = 0
    loop:
        SELECT id, index_name, content
        FROM partition_table
        OFFSET offset LIMIT batch_size

        若无结果 → 跳出循环

        新模型嵌入全部 content → 得到 [(id, embedding, search_vector), ...]
        执行单条 SQL:

        UPDATE {base_table} SET
            embedding = new_embedding,
            search_vector = to_tsvector('simple', content),
            updated_at = now()
        FROM (VALUES
            (%(id1)s, %(idx1)s, %(emb1)s),
            (%(id2)s, %(idx2)s, %(emb2)s),
            ...
        ) AS vals(id, idx, emb)
        WHERE base_table.id = vals.id
          AND base_table.index_name = vals.idx

        offset += batch_size
```

使用 `base_table`（而非 partition）是因为 PG 支持跨 partition 的 UPDATE 路由。

### 维度变化场景

```
1. 记录所有需要重建的 partition 列表
2. 对每个 partition:
   a. DROP INDEX {partition_name}_id_uidx
   b. DROP INDEX {partition_name}_embedding_idx (HNSW)
   c. 添加新列 embedding_new vector(new_dim)
   d. 逐批次嵌入并 UPDATE embedding_new
   e. ALTER TABLE {partition} DROP COLUMN embedding
   f. ALTER TABLE {partition} RENAME COLUMN embedding_new TO embedding
   g. ALTER TABLE {base_table} ALTER COLUMN embedding TYPE vector(new_dim)
   h. 重建唯一索引 + HNSW 索引
```

分列置换（而非直接 ALTER TYPE）的考虑：
- pgvector 的 vector(N) ALTER TYPE 会锁全表并 rewrite
- 新列 + 批次写入 + DROP + RENAME 的锁窗口极小（DDL 瞬间）
- 写入完成后重建 HNSW 索引

## ElasticsearchVectorStore 实现

### 维度不变场景

```
for each index in target_indexes:
    scroll API 遍历所有文档 (batch_size)
    for each scroll batch:
        新模型嵌入全部 content
        bulk update:
            {"update": {"_index": index, "_id": doc_id}}
            {"doc": {"embedding": new_vector}}
    清理 scroll context
```

### 维度变化场景

ES 7.x+ 的 `dense_vector` mapping 固定字段维度，维度变了必须重建索引：

```
for each index in target_indexes:
    1. 读取旧 index mapping + settings
    2. 创建 index_v2（临时候选名）
       - mapping 中 embedding 字段声明新维度
       - 其余 mapping / settings 继承旧 index
    3. scroll 旧 index，每批：
       a. 新模型嵌入 content
       b. bulk index 到 index_v2（保留 _id）
    4. _reindex 完成后：
       a. 删除旧 index（或保留旧 index 作备份）
       b. 创建同名别名：旧 index 名 → index_v2
       c. 更新完成后可根据配置决定是否删除旧 index
```

## 各文件改动清单

| 文件 | 改动 |
|---|---|
| `deepclaw/common/vector_store/base.py` | 新增具体 `refresh_embeddings` 模板方法 + 抽象钩子 `_ensure_refresh_dimensions` / `_refresh_embeddings_batch` |
| `deepclaw/common/vector_store/pgsql.py` | 实现 `_ensure_refresh_dimensions` + `_refresh_embeddings_batch` |
| `deepclaw/common/vector_store/elasticsearch.py` | 实现 `_ensure_refresh_dimensions` + `_refresh_embeddings_batch` |
| `deepclaw/common/vector_store/__init__.py` | 确认导出不受影响 |

## 未覆盖事项（YAGNI）

- pgvector 的 ivfflat 索引。当前代码统一使用 HNSW，ivfflat 索引类型暂不考虑
- ES index template / ILM 策略。重建索引时只拷贝 mapping + settings，不处理 template 层
- 渐近式刷新（只刷新 delta）。当前是全量重算，后续可按需优化
- 并发多线程嵌入。当前是单线程批次串行，批量嵌入由模型内部并行
