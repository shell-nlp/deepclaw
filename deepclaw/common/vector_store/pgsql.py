from __future__ import annotations

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
    ):
        self.database_url = database_url
        self._embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.table_name = table_name
        self.schema_name = schema_name
        self._dimension_verified: bool = False

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            from deepclaw.utils import get_embedding_model

            self._embedding_model = get_embedding_model()
        return self._embedding_model

    def _connect(self):
        conn = psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _qualified_table_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}"

    def _partition_table_name(self, index_name: str) -> str:
        normalized = "".join(char if char.isalnum() else "_" for char in index_name.lower())
        normalized = normalized.strip("_") or "default"
        return f"{self.table_name}_{normalized}"

    def _qualified_partition_name(self, index_name: str) -> str:
        return f"{self.schema_name}.{self._partition_table_name(index_name)}"

    def _bm25_index_name(self, index_name: str) -> str:
        return f"{self._partition_table_name(index_name)}_bm25_idx"

    def _vector_index_name(self, index_name: str) -> str:
        return f"{self._partition_table_name(index_name)}_embedding_idx"

    def _search_vector_index_name(self, index_name: str) -> str:
        return f"{self._partition_table_name(index_name)}_search_vector_idx"

    def _ensure_embedding_dimensions(self, embedding: list[float]) -> int:
        if self.embedding_dimensions is None:
            self.embedding_dimensions = len(embedding)
        return self.embedding_dimensions

    def _ensure_column_dimension(self, target_dim: int) -> None:
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
        if index_names:
            raise ValueError(f"{operation} operations only support a single index_name")
        if not index_name:
            raise ValueError(f"index_name is required for {operation} operations")
        return index_name

    def _ensure_base_schema(self) -> None:
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
        self._ensure_base_schema()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT index_name FROM {self._qualified_table_name()} ORDER BY index_name"
            )
            rows = cur.fetchall()
        return [row["index_name"] for row in rows]

    def _resolve_read_indexes(
        self,
        *,
        index_name: str | None = None,
        index_names: list[str] | None = None,
    ) -> list[str]:
        target_indexes = self.resolve_index_names(index_name=index_name, index_names=index_names)
        if target_indexes is not None:
            return target_indexes
        return self._list_index_names()

    def _apply_min_similarity(
        self,
        candidates: list[dict[str, Any]],
        min_similarity: float | None,
    ) -> list[dict[str, Any]]:
        if min_similarity is None:
            return candidates
        return [item for item in candidates if item.get("score") is None or item["score"] >= min_similarity]

    def _row_to_result(self, row: dict[str, Any]) -> dict[str, Any]:
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
        index_name = self._require_single_index_name(index_name=index_name, operation="delete")
        self._ensure_base_schema()
        sql = f"DELETE FROM {self._qualified_table_name()} WHERE index_name = %(index_name)s AND id = %(id)s"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, {"index_name": index_name, "id": doc_id})
            return cur.rowcount > 0

    def delete_batch(self, doc_ids: list[str], index_name: str | None = None) -> list[bool]:
        index_name = self._require_single_index_name(index_name=index_name, operation="delete_batch")
        if not doc_ids:
            return []
        deleted = []
        for doc_id in doc_ids:
            deleted.append(self.delete(doc_id, index_name=index_name))
        return deleted

    def get(self, doc_id: str, index_name: str | None = None) -> dict[str, Any] | None:
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
        target_indexes = self._resolve_read_indexes(index_name=index_name, index_names=index_names)
        if not target_indexes:
            return []

        rows = self._fetch_keyword_rows(query=query, index_names=target_indexes, limit=k)
        return [self._row_to_result(row) for row in rows]
