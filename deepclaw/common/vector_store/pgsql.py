from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Json
from loguru import logger

from deepclaw.common.vector_store.base import AbstractVectorStore


class PgVectorStore(AbstractVectorStore):
    """基于 PostgreSQL + pgvector + pg_search 的向量库实现。"""

    def __init__(
        self,
        database_url: str,
        *,
        embedding_model=None,
        embedding_dimensions: int | None = None,
        table_name: str = "vector_store_documents",
        schema_name: str = "public",
        refresh_fail_dir: str | Path = ".",
    ):
        """初始化 PgVectorStore 实例。

        Args:
            database_url: PostgreSQL 数据库连接 URL。
            embedding_model: 嵌入模型实例，为 None 时延迟加载。
            embedding_dimensions: 向量维度，为 None 时自动从首次嵌入推断。
            table_name: 基表名称，用于分区表命名。
            schema_name: 数据库 schema 名称。
            refresh_fail_dir: refresh 失败记录写出目录。
        """
        self.database_url = database_url
        self._embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.table_name = table_name
        self.schema_name = schema_name
        self._refresh_fail_dir = Path(refresh_fail_dir)
        self._dimension_verified: bool = False

    @property
    def embedding_model(self):
        """获取嵌入模型实例，未初始化时延迟创建。"""
        if self._embedding_model is None:
            from deepclaw.utils import get_embedding_model

            self._embedding_model = get_embedding_model()
        return self._embedding_model

    def _connect(self):
        """建立并返回与 PostgreSQL 的连接，自动注册 pgvector 类型。"""
        conn = psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _qualified_table_name(self) -> str:
        """返回带 schema 的完整基表名称。"""
        return f"{self.schema_name}.{self.table_name}"

    def _partition_table_name(self, index_name: str) -> str:
        """根据 index_name 生成分区表名称，非法字符替换为下划线。

        Args:
            index_name: 索引名称。
        """
        normalized = "".join(char if char.isalnum() else "_" for char in index_name.lower())
        normalized = normalized.strip("_") or "default"
        return f"{self.table_name}_{normalized}"

    def _qualified_partition_name(self, index_name: str) -> str:
        """返回带 schema 的完整分区表名称。

        Args:
            index_name: 索引名称。
        """
        return f"{self.schema_name}.{self._partition_table_name(index_name)}"

    def _bm25_index_name(self, index_name: str) -> str:
        """返回全文检索 BM25 索引的名称。

        Args:
            index_name: 索引名称。
        """
        return f"{self._partition_table_name(index_name)}_bm25_idx"

    def _vector_index_name(self, index_name: str) -> str:
        """返回 HNSW 向量索引的名称。

        Args:
            index_name: 索引名称。
        """
        return f"{self._partition_table_name(index_name)}_embedding_idx"

    def _search_vector_index_name(self, index_name: str) -> str:
        """返回 tsvector GIN 索引的名称。

        Args:
            index_name: 索引名称。
        """
        return f"{self._partition_table_name(index_name)}_search_vector_idx"

    def _ensure_embedding_dimensions(self, embedding: list[float]) -> int:
        """确保 embedding_dimensions 已设置，未设置时从传入向量推断。

        Args:
            embedding: 嵌入向量。

        Returns:
            确定的向量维度。
        """
        if self.embedding_dimensions is None:
            self.embedding_dimensions = len(embedding)
        return self.embedding_dimensions

    def _ensure_column_dimension(self, target_dim: int) -> None:
        """检查并调整表的 embedding 列维度以匹配目标维度。

        Args:
            target_dim: 目标向量维度。
        """
        with self._connect() as conn, conn.cursor() as cur:
            # pgvector 的 vector(N) 类型，维度存储在 pg_attribute.atttypmod 中
            # atttypmod = 维度 + 4 (VARHDRSZ)
            cur.execute(
                f"SELECT atttypmod FROM pg_catalog.pg_attribute "
                f"WHERE attrelid = '{self._qualified_table_name()}'::regclass "
                f"AND attname = 'embedding' "
                f"AND attnum > 0 AND NOT attisdropped"
            )
            row = cur.fetchone()
            if row is not None:
                current_dim = row["atttypmod"] - 4
                if current_dim != target_dim:
                    logger.info(
                        "向量维度不匹配: 表中有 {} 维, 目标 {} 维, 执行 ALTER COLUMN", current_dim, target_dim
                    )
                    cur.execute(
                        f"ALTER TABLE {self._qualified_table_name()} "
                        f"ALTER COLUMN embedding TYPE vector({target_dim}) "
                        f"USING embedding::vector({target_dim})"
                    )

    def _require_single_index_name(
        self,
        *,
        index_name: str | None = None,
        index_names: list[str] | None = None,
        operation: str = "write",
    ) -> str:
        """强制要求提供一个且仅一个 index_name，不支持多索引操作。

        Args:
            index_name: 单个索引名称。
            index_names: 索引名称列表（不允许传入）。
            operation: 操作名称，用于异常提示。

        Returns:
            校验后的 index_name。

        Raises:
            ValueError: 当 index_names 非空或 index_name 为空时抛出。
        """
        if index_names:
            raise ValueError(f"{operation} operations only support a single index_name")
        if not index_name:
            raise ValueError(f"index_name is required for {operation} operations")
        return index_name

    def _ensure_base_schema(self) -> None:
        """确保基础表结构存在，包括 vector 和 pg_search 扩展及分区基表。"""
        dimensions = self.embedding_dimensions or 1536
        sql = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS pg_search;
        CREATE TABLE IF NOT EXISTS {self._qualified_table_name()} (
            id text NOT NULL,
            index_name text NOT NULL,
            content text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            embedding vector({dimensions}) NOT NULL,
            search_vector tsvector NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (index_name, id)
        ) PARTITION BY LIST (index_name);
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
        if self.embedding_dimensions is not None and not self._dimension_verified:
            self._ensure_column_dimension(self.embedding_dimensions)
            self._dimension_verified = True

    def _ensure_partition(self, index_name: str) -> None:
        """确保指定 index_name 的分区表及各类索引已创建。

        Args:
            index_name: 索引名称。
        """
        partition_table = self._qualified_partition_name(index_name)
        partition_name = self._partition_table_name(index_name)
        bm25_index_name = self._bm25_index_name(index_name)
        vector_index_name = self._vector_index_name(index_name)
        search_vector_index_name = self._search_vector_index_name(index_name)

        escaped = index_name.replace("'", "''")
        statements = [
            f"""
            CREATE TABLE IF NOT EXISTS {partition_table}
            PARTITION OF {self._qualified_table_name()}
            FOR VALUES IN ('{escaped}')
            """,
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {partition_name}_id_uidx
            ON {partition_table} (id)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS {search_vector_index_name}
            ON {partition_table}
            USING GIN (search_vector)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS {vector_index_name}
            ON {partition_table}
            USING hnsw (embedding vector_cosine_ops)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS {bm25_index_name}
            ON {partition_table}
            USING bm25 (id, content)
            WITH (key_field='id')
            """,
        ]
        with self._connect() as conn, conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)

    def _list_index_names(self) -> list[str]:
        """查询基表中所有不同的 index_name，确保基础表结构存在。"""
        self._ensure_base_schema()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT index_name FROM {self._qualified_table_name()} ORDER BY index_name"
            )
            rows = cur.fetchall()
        return [row["index_name"] for row in rows]

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

    def _ensure_refresh_dimensions(self, new_dim: int, index_names: list[str]) -> None:
        """PG 维度适配：同维度跳过，不同维度则添加 embedding_new 列并删除旧索引。"""
        if self.embedding_dimensions == new_dim:
            self._needs_reindex = set()
            return
        # 维度变化时：先删旧索引，再新增临时列 embedding_new(vector(new_dim))
        for index_name in index_names:
            partition_table = self._qualified_partition_name(index_name)
            vector_idx = self._vector_index_name(index_name)
            uid_idx = f"{self._partition_table_name(index_name)}_id_uidx"
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(f"DROP INDEX IF EXISTS {vector_idx}")
                cur.execute(f"DROP INDEX IF EXISTS {uid_idx}")
                cur.execute(
                    f"ALTER TABLE {partition_table} "
                    f"ADD COLUMN IF NOT EXISTS embedding_new vector({new_dim})"
                )
            self._needs_reindex.add(index_name)
        self.embedding_dimensions = new_dim

    def _init_refresh_batch(self, index_name: str, batch_size: int) -> None:
        """PG 批次初始化：重置 OFFSET 游标。"""
        self._pg_refresh_offset = 0

    def _fetch_refresh_batch(self, index_name: str, batch_size: int) -> list[dict[str, Any]]:
        """PG 批次获取：OFFSET/LIMIT 翻页，按 id 排序保证顺序稳定。"""
        self._ensure_base_schema()
        self._ensure_partition(index_name)
        table = self._qualified_table_name()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, content, index_name "
                f"FROM {table} "
                f"WHERE index_name = %(index_name)s "
                f"ORDER BY id "
                f"OFFSET %(offset)s LIMIT %(limit)s",
                {
                    "index_name": index_name,
                    "offset": self._pg_refresh_offset,
                    "limit": batch_size,
                },
            )
            rows = cur.fetchall()
        self._pg_refresh_offset += batch_size
        return [
            {"id": str(row["id"]), "content": row["content"], "index_name": row["index_name"]}
            for row in rows
        ]

    def _refresh_embeddings_batch(
        self,
        docs: list[dict[str, Any]],
        new_embedding_model,
        index_name: str,
    ) -> tuple[int, int]:
        """PG 批量更新：用 VALUES 构造临时表一次 UPDATE 全部文档的向量。

        维度和前一致时写 embedding 列，否则写 embedding_new 列；
        同步更新 search_vector 和 updated_at。
        批量失败时逐条回退，避免单条错误拖垮整个批次。
        """
        if not docs:
            return (0, 0)
        try:
            embeddings = new_embedding_model.embed_documents([doc["content"] for doc in docs])
        except Exception:
            logger.error("嵌入失败: {}", [doc.get("id", "unknown") for doc in docs])
            return (0, len(docs))

        # 维度变化时写入临时列 embedding_new，否则直接覆盖原列
        embed_col = "embedding_new" if self._needs_reindex else "embedding"
        partition_table = self._qualified_partition_name(index_name)
        values_placeholders = ", ".join(
            f"(%(id_{i})s, %(embedding_{i})s)" for i in range(len(docs))
        )
        params: dict[str, Any] = {}
        for i, doc in enumerate(docs):
            params[f"id_{i}"] = doc["id"]
            params[f"embedding_{i}"] = embeddings[i]

        # UPDATE ... FROM (VALUES) 实现一次 SQL 更新整批文档
        sql = f"""
        UPDATE {partition_table} AS p
        SET {embed_col} = v.embedding,
            search_vector = to_tsvector('simple', p.content),
            updated_at = now()
        FROM (VALUES {values_placeholders}) AS v(id, embedding)
        WHERE p.id = v.id
        """
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(sql, params)
            return (len(docs), 0)
        except Exception as exc:
            logger.warning("批量嵌入写入失败, 逐条回退: {}", exc)
            success = 0
            fail = 0
            with self._connect() as conn, conn.cursor() as cur:
                for i, doc in enumerate(docs):
                    try:
                        cur.execute(
                            f"UPDATE {partition_table} "
                            f"SET {embed_col} = %(embedding)s, "
                            f"    search_vector = to_tsvector('simple', %(content)s), "
                            f"    updated_at = now() "
                            f"WHERE id = %(id)s",
                            {"id": doc["id"], "embedding": embeddings[i], "content": doc["content"]},
                        )
                        success += 1
                    except Exception:
                        fail += 1
            return (success, fail)

    def _finalize_refresh(self) -> None:
        """PG refresh 收尾：对维度变化的索引做列置换（DROP + RENAME）。"""
        if not self._needs_reindex:
            return
        for index_name in self._needs_reindex:
            partition_table = self._qualified_partition_name(index_name)
            # 检查是否确实有 embedding_new 列（幂等）
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = %(schema)s "
                    "AND table_name = %(table)s "
                    "AND column_name = 'embedding_new'",
                    {
                        "schema": self.schema_name,
                        "table": self._partition_table_name(index_name),
                    },
                )
                has_new_column = cur.fetchone() is not None
            if has_new_column:
                with self._connect() as conn, conn.cursor() as cur:
                    cur.execute(f"ALTER TABLE {partition_table} DROP COLUMN embedding")
                    cur.execute(f"ALTER TABLE {partition_table} RENAME COLUMN embedding_new TO embedding")
            # 重建向量索引以支持新维度
            self._ensure_partition(index_name)

    def _resolve_read_indexes(
        self,
        *,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[str]:
        """解析查询操作的目标索引列表，优先使用传入参数，否则返回全量索引。

        Args:
            index_name: 单个索引名称。
            index_names: 索引名称列表。

        Returns:
            目标索引名称列表。
        """
        target_indexes = self.resolve_index_names(index_name=index_name, index_names=index_names)
        if target_indexes is not None:
            return target_indexes
        return self._list_index_names()

    def _apply_min_similarity(
        self,
        candidates: list[dict[str, Any]],
        min_similarity: float | None,
    ) -> list[dict[str, Any]]:
        """过滤候选结果，保留满足最低相似度阈值的结果。

        Args:
            candidates: 候选结果列表，每项应包含可选的 score 字段。
            min_similarity: 最低相似度阈值，为 None 时不过滤。

        Returns:
            过滤后的结果列表。
        """
        if min_similarity is None:
            return candidates
        return [item for item in candidates if item.get("score") is None or item["score"] >= min_similarity]

    def _row_to_result(self, row: dict[str, Any]) -> dict[str, Any]:
        """将数据库行转换为统一的返回结果字典。

        Args:
            row: 数据库查询结果行。

        Returns:
            包含 id、content、metadata 和可选的 score 的字典。
        """
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = {"raw": metadata}
        metadata = dict(metadata)
        if row.get("index_name") is not None:
            metadata.setdefault("index_name", row["index_name"])
        result = {
            "id": str(row["id"]),
            "content": row.get("content", ""),
            "metadata": metadata,
        }
        if row.get("score") is not None:
            result["score"] = float(row["score"])
        return result

    def _fetch_keyword_rows(
        self,
        *,
        query: str,
        index_names: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        """执行关键词全文检索查询，返回匹配行。

        Args:
            query: 检索关键词。
            index_names: 要检索的索引名称列表。
            limit: 返回结果数量上限。

        Returns:
            查询结果行列表。
        """
        self._ensure_base_schema()
        for index_name in index_names:
            self._ensure_partition(index_name)
        sql = f"""
        SELECT id, index_name, content, metadata, pdb.score(id) AS score
        FROM {self._qualified_table_name()}
        WHERE index_name = ANY(%(index_names)s)
          AND content ||| %(query)s
        ORDER BY score DESC
        LIMIT %(limit)s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, {"index_names": index_names, "query": query, "limit": limit})
            return cur.fetchall()

    def _fetch_vector_candidates(
        self,
        *,
        index_name: str,
        query_vector: list[float],
        limit: int,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """在指定索引分区中执行向量相似度检索，返回候选结果。

        Args:
            index_name: 目标分区索引名称。
            query_vector: 查询向量。
            limit: 返回候选数量上限。
            filter_conditions: 元数据过滤条件字典。

        Returns:
            查询结果行列表。
        """
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

    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        index_name: str | None = None,
    ) -> str:
        """向向量库中添加一条文档记录。

        Args:
            content: 文档内容。
            metadata: 文档元数据。
            doc_id: 文档 ID，为空时从 metadata 中提取。
            index_name: 目标索引名称。

        Returns:
            添加的文档 ID。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="add")
        embedding = self.embedding_model.embed_query(content)
        self._ensure_embedding_dimensions(embedding)
        self._ensure_base_schema()
        self._ensure_partition(index_name)
        document_id = doc_id or str((metadata or {}).get("id") or "")
        if not document_id:
            raise ValueError("doc_id is required for PgVectorStore add operations")

        sql = f"""
        INSERT INTO {self._qualified_table_name()} (
            id, index_name, content, metadata, embedding, search_vector
        )
        VALUES (
            %(id)s,
            %(index_name)s,
            %(content)s,
            %(metadata)s,
            %(embedding)s,
            to_tsvector('simple', %(content)s)
        )
        ON CONFLICT (index_name, id) DO UPDATE SET
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            search_vector = EXCLUDED.search_vector,
            updated_at = now()
        """
        params = {
            "id": document_id,
            "index_name": index_name,
            "content": content,
            "metadata": Json(metadata or {}),
            "embedding": embedding,
        }
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
        return document_id

    def add_batch(
        self,
        documents: list[dict[str, Any]],
        index_name: str | None = None,
    ) -> list[str]:
        """批量添加文档到向量库。

        Args:
            documents: 文档字典列表，每项应包含 content、可选的 metadata 和 id。
            index_name: 目标索引名称。

        Returns:
            添加成功的文档 ID 列表。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="add_batch")
        if not documents:
            return []
        added_ids = []
        for document in documents:
            doc_id = str(document.get("id") or document.get("metadata", {}).get("id") or "")
            added_ids.append(
                self.add(
                    content=document.get("content", ""),
                    metadata=document.get("metadata"),
                    doc_id=doc_id,
                    index_name=index_name,
                )
            )
        return added_ids

    def update(
        self,
        doc_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        index_name: str | None = None,
    ) -> bool:
        """更新向量库中指定文档的内容和/或元数据。

        Args:
            doc_id: 文档 ID。
            content: 新的文档内容，为 None 时不更新。
            metadata: 新的文档元数据，为 None 时不更新。
            index_name: 索引名称。

        Returns:
            是否成功更新。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="update")
        if content is None and metadata is None:
            return False

        self._ensure_base_schema()
        self._ensure_partition(index_name)
        assignments = ["updated_at = now()"]
        params: dict[str, Any] = {"id": doc_id, "index_name": index_name}
        if content is not None:
            embedding = self.embedding_model.embed_query(content)
            self._ensure_embedding_dimensions(embedding)
            assignments.extend(
                [
                    "content = %(content)s",
                    "embedding = %(embedding)s",
                    "search_vector = to_tsvector('simple', %(content)s)",
                ]
            )
            params["content"] = content
            params["embedding"] = embedding
        if metadata is not None:
            assignments.append("metadata = %(metadata)s")
            params["metadata"] = Json(metadata)

        sql = f"""
        UPDATE {self._qualified_table_name()}
        SET {", ".join(assignments)}
        WHERE index_name = %(index_name)s AND id = %(id)s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount > 0

    def delete(self, doc_id: str, index_name: str | None = None) -> bool:
        """从向量库中删除指定文档。

        Args:
            doc_id: 文档 ID。
            index_name: 索引名称。

        Returns:
            是否成功删除。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="delete")
        self._ensure_base_schema()
        sql = f"DELETE FROM {self._qualified_table_name()} WHERE index_name = %(index_name)s AND id = %(id)s"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, {"index_name": index_name, "id": doc_id})
            return cur.rowcount > 0

    def delete_batch(self, doc_ids: list[str], index_name: str | None = None) -> list[bool]:
        """批量从向量库中删除指定文档。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 索引名称。

        Returns:
            每项表示对应文档是否成功删除。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="delete_batch")
        if not doc_ids:
            return []
        deleted = []
        for doc_id in doc_ids:
            deleted.append(self.delete(doc_id, index_name=index_name))
        return deleted

    def get(self, doc_id: str, index_name: str | None = None) -> dict[str, Any] | None:
        """根据文档 ID 获取指定文档。

        Args:
            doc_id: 文档 ID。
            index_name: 索引名称。

        Returns:
            文档字典，不存在时返回 None。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="get")
        self._ensure_base_schema()
        sql = f"""
        SELECT id, index_name, content, metadata
        FROM {self._qualified_table_name()}
        WHERE index_name = %(index_name)s AND id = %(id)s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, {"index_name": index_name, "id": doc_id})
            row = cur.fetchone()
        return self._row_to_result(row) if row else None

    def exists(self, doc_id: str, index_name: str | None = None) -> bool:
        """检查指定文档是否存在。

        Args:
            doc_id: 文档 ID。
            index_name: 索引名称。

        Returns:
            文档是否存在。
        """
        index_name = self._require_single_index_name(index_name=index_name, operation="exists")
        self._ensure_base_schema()
        sql = f"SELECT 1 FROM {self._qualified_table_name()} WHERE index_name = %(index_name)s AND id = %(id)s"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, {"index_name": index_name, "id": doc_id})
            return cur.fetchone() is not None

    def count(
        self,
        filter_conditions: dict[str, Any] | None = None,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> int:
        """统计符合条件的文档数量。

        Args:
            filter_conditions: 过滤条件字典。
            index_name: 单个索引名称。
            index_names: 索引名称列表。

        Returns:
            文档数量。
        """
        target_indexes = self._resolve_read_indexes(index_name=index_name, index_names=index_names)
        self._ensure_base_schema()
        where_clauses = ["index_name = ANY(%(index_names)s)"]
        params: dict[str, Any] = {"index_names": target_indexes}
        if filter_conditions:
            for idx, (field, value) in enumerate(filter_conditions.items()):
                param_name = f"value_{idx}"
                if field.startswith("metadata."):
                    metadata_key = field.split(".", 1)[1]
                    where_clauses.append(f"metadata ->> '{metadata_key}' = %({param_name})s")
                else:
                    where_clauses.append(f"{field} = %({param_name})s")
                params[param_name] = str(value)
        sql = f"""
        SELECT COUNT(*) AS count
        FROM {self._qualified_table_name()}
        WHERE {" AND ".join(where_clauses)}
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return int(row["count"]) if row else 0

    def search(
        self,
        query: str | None = None,
        k: int = 3,
        filter_conditions: dict[str, Any] | None = None,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """通用检索入口，有 query 时走关键词检索，否则按更新时间排序返回最新文档。

        Args:
            query: 检索关键词，为空时返回最新文档。
            k: 返回结果数量。
            filter_conditions: 过滤条件字典。
            index_name: 单个索引名称。
            index_names: 索引名称列表。

        Returns:
            检索结果列表。
        """
        target_indexes = self._resolve_read_indexes(index_name=index_name, index_names=index_names)
        if query:
            return self.keyword_search(query, k=k, index_names=target_indexes)

        self._ensure_base_schema()
        where_clauses = ["index_name = ANY(%(index_names)s)"]
        params: dict[str, Any] = {"index_names": target_indexes, "limit": k}
        if filter_conditions:
            for idx, (field, value) in enumerate(filter_conditions.items()):
                param_name = f"value_{idx}"
                if field.startswith("metadata."):
                    metadata_key = field.split(".", 1)[1]
                    where_clauses.append(f"metadata ->> '{metadata_key}' = %({param_name})s")
                else:
                    where_clauses.append(f"{field} = %({param_name})s")
                params[param_name] = str(value)
        sql = f"""
        SELECT id, index_name, content, metadata
        FROM {self._qualified_table_name()}
        WHERE {" AND ".join(where_clauses)}
        ORDER BY updated_at DESC
        LIMIT %(limit)s
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [self._row_to_result(row) for row in rows]

    def vector_search(
        self,
        query: str,
        k: int = 3,
        index_name: str | None = None,
        index_names: list[str] | None = None,
        min_similarity: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """向量相似度检索，查询文本经嵌入后使用余弦距离检索。

        Args:
            query: 查询文本。
            k: 返回结果数量。
            index_name: 单个索引名称。
            index_names: 索引名称列表。
            min_similarity: 最低相似度阈值，低于该值的结果被过滤。
            filter_conditions: 元数据过滤条件字典。

        Returns:
            按相似度降序排列的检索结果列表。
        """
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

    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """全文关键词检索，使用 pg_search 的 BM25 评分。

        Args:
            query: 检索关键词。
            k: 返回结果数量。
            index_name: 单个索引名称。
            index_names: 索引名称列表。

        Returns:
            按 BM25 评分降序排列的检索结果列表。
        """
        target_indexes = self._resolve_read_indexes(index_name=index_name, index_names=index_names)
        if not target_indexes:
            return []

        rows = self._fetch_keyword_rows(query=query, index_names=target_indexes, limit=k)
        return [self._row_to_result(row) for row in rows]

    def refresh_embeddings(
        self,
        new_embedding_model=None,
        *,
        batch_size: int = 50,
        index_names: list[str] | None = None,
    ) -> tuple[int, int]:
        """用新嵌入模型刷新所有已有文档的向量。

        PG 实现：列置换策略，维度变化时使用临时列 embedding_new，
        最终 _finalize_refresh 做 DROP + RENAME 完成迁移。
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
