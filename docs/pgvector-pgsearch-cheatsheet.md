# PgVector + PgSearch 备忘

这份文档用于快速说明当前仓库里独立 `PgVector` 环境的用法，以及 `pg_search` / `pgvector` 的常见 SQL。

## 1. 环境入口

独立的增强版 PostgreSQL 使用：

```bash
docker compose -f docker-compose.pgvector.yml up -d
```

连接串：

```bash
postgresql://admin:admin@localhost:55432/deepclaw
```

停止：

```bash
docker compose -f docker-compose.pgvector.yml down
```

连数据卷一起删除：

```bash
docker compose -f docker-compose.pgvector.yml down -v
```

## 2. 当前已启用的扩展

当前独立数据库启动后会自动启用：

- `vector`
- `pg_search`

初始化脚本位于：

- `docker/postgresql/initdb/01-enable-hybrid-search.sql`

## 3. `paradedb` 和 `pdb` 是什么

当前库里这两个 schema 都存在：

- `paradedb`
- `pdb`

它们的关系是：

- `paradedb`：`pg_search` 的主 schema，扩展本体主要安装在这里
- `pdb`：查询时常用的快捷 schema，常见函数如 `pdb.score(...)` 会从这里调用

可以简单理解为：

- `paradedb` = 扩展本体
- `pdb` = 查询快捷入口

## 4. 最小建表示例

```sql
CREATE TABLE documents (
    id bigserial PRIMARY KEY,
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(3) NOT NULL
);
```

插入示例数据：

```sql
INSERT INTO documents (content, metadata, embedding)
VALUES
    ('hello vector world', '{"source":"demo"}', '[0.1,0.2,0.3]'),
    ('bm25 keyword search', '{"source":"demo"}', '[0.3,0.2,0.1]');
```

## 5. BM25 索引和查询

### 5.1 创建 BM25 索引

`pg_search` 的 BM25 索引可以这样建：

```sql
CREATE INDEX documents_bm25_idx
ON documents
USING bm25 (id, content)
WITH (key_field='id');
```

注意：

- `key_field` 必须指向唯一键，通常就是主键
- `id` 需要放在索引字段列表里
- 一个表通常只维护一个覆盖常用字段的 BM25 索引更合适

### 5.2 BM25 查询

最常见的查询写法：

```sql
SELECT id, content, pdb.score(id) AS score
FROM documents
WHERE content ||| 'vector'
ORDER BY score DESC
LIMIT 10;
```

说明：

- `|||`：匹配任意词，偏 OR 语义
- `&&&`：匹配全部词，偏 AND 语义
- `pdb.score(id)`：返回 BM25 分数

示例：

```sql
SELECT id, content, pdb.score(id) AS score
FROM documents
WHERE content &&& 'keyword search'
ORDER BY score DESC
LIMIT 10;
```

## 6. 向量检索

最简单的向量相似度查询：

```sql
SELECT
    id,
    content,
    1 - (embedding <=> '[0.1,0.2,0.3]'::vector) AS score
FROM documents
ORDER BY embedding <=> '[0.1,0.2,0.3]'::vector
LIMIT 10;
```

说明：

- `<=>`：余弦距离
- 常见做法是把 `1 - distance` 作为相似度分数

### 6.1 向量索引

可以加 `hnsw` 索引：

```sql
CREATE INDEX documents_embedding_idx
ON documents
USING hnsw (embedding vector_cosine_ops);
```

## 7. 混合检索思路

当前仓库里 `PgVectorStore` 的方向是：

1. 先做向量检索
2. 再做 BM25 检索
3. 按文档内容去重
4. 合并结果

如果你要手写 SQL 做混合检索，最简单可以分两步：

- 先查 BM25 top-k
- 再查向量 top-k
- 在应用层合并

如果后面要进一步增强，可以考虑：

- RRF（Reciprocal Rank Fusion）
- 统一归一化分数后重排

## 8. 常用检查 SQL

### 8.1 看扩展是否安装

```sql
SELECT extname, extnamespace::regnamespace
FROM pg_extension
WHERE extname IN ('vector', 'pg_search');
```

### 8.2 看 schema 是否存在

```sql
SELECT nspname
FROM pg_namespace
WHERE nspname IN ('paradedb', 'pdb');
```

### 8.3 看 BM25 相关函数

```sql
SELECT proname, n.nspname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('paradedb', 'pdb')
ORDER BY n.nspname, proname;
```

## 9. 当前仓库里的对应关系

当前仓库中：

- 主环境 `docker-compose.yml`
  - 保持原样
  - 不包含 PgVector/BM25 增强版 PostgreSQL

- 独立增强环境 `docker-compose.pgvector.yml`
  - 提供 `pgvector + pg_search`
  - 端口为 `55432`

- 自定义 PostgreSQL 镜像
  - `docker/postgresql/Dockerfile`

- 初始化扩展脚本
  - `docker/postgresql/initdb/01-enable-hybrid-search.sql`

## 10. 一个完整 smoke test

```sql
DROP TABLE IF EXISTS hybrid_smoke_test;

CREATE TABLE hybrid_smoke_test (
    id bigserial PRIMARY KEY,
    content text NOT NULL,
    embedding vector(3) NOT NULL
);

INSERT INTO hybrid_smoke_test (content, embedding)
VALUES
    ('hello vector world', '[0.1,0.2,0.3]'),
    ('bm25 keyword search', '[0.3,0.2,0.1]');

CREATE INDEX hybrid_smoke_test_bm25_idx
ON hybrid_smoke_test
USING bm25 (id, content)
WITH (key_field='id');

SELECT id, content, pdb.score(id) AS score
FROM hybrid_smoke_test
WHERE content ||| 'vector'
ORDER BY score DESC;

SELECT
    id,
    content,
    1 - (embedding <=> '[0.1,0.2,0.3]'::vector) AS score
FROM hybrid_smoke_test
ORDER BY embedding <=> '[0.1,0.2,0.3]'::vector
LIMIT 2;

DROP TABLE hybrid_smoke_test;
```
