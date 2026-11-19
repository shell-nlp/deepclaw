"""基于 SQLite + sqlite-vec 的轻量向量库实现。

默认后端：无需任何外部中间件，单个文件同时保存文档、元数据与向量。
关键词检索用子串命中加 Python 打分，避免 SQLite 原生分词对中文失效。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import sqlite_vec

from deepclaw.common.vector_store.base import AbstractVectorStore

_CHUNKS_TABLE = "vec_chunks"
_INDEX_META_TABLE = "vec_index_meta"
_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z_]+")


def _utc_now() -> str:
    """返回写入记录使用的 UTC 时间文本。

    Returns:
        ISO 8601 格式的 UTC 时间。
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


class SqliteVecVectorStore(AbstractVectorStore):
    """基于 sqlite-vec 的单文件向量库。

    Args:
        db_path: SQLite 数据库文件路径。
        embedding_model: 嵌入模型实例，为 None 时延迟加载。
        embedding_dimensions: 向量维度，为 None 时按首次嵌入推断。
    """

    _ddl_lock = threading.Lock()

    def __init__(
        self,
        db_path: str | Path,
        *,
        embedding_model=None,
        embedding_dimensions: int | None = None,
    ) -> None:
        """初始化 SQLite 向量库。

        Args:
            db_path: SQLite 数据库文件路径。
            embedding_model: 嵌入模型实例。
            embedding_dimensions: 向量维度。
        """
        self.db_path = Path(db_path)
        self._embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions

    @property
    def embedding_model(self):
        """获取嵌入模型实例，未初始化时延迟创建。"""
        if self._embedding_model is None:
            from deepclaw.utils import get_embedding_model

            self._embedding_model = get_embedding_model()
        return self._embedding_model

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """打开数据库连接并加载 sqlite-vec 扩展。

        Yields:
            已启用向量扩展的 SQLite 连接；退出时提交并关闭。
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _table_name(self, index_name: str) -> str:
        """把索引名映射为合法的虚拟表名。

        Args:
            index_name: 业务索引名称。

        Returns:
            只含小写字母、数字和下划线的虚拟表名。
        """
        normalized = "".join(char if char.isalnum() else "_" for char in index_name.lower())
        normalized = normalized.strip("_") or "default"
        digest = hashlib.sha1(index_name.encode("utf-8")).hexdigest()[:8]
        return f"vec_{normalized[:40]}_{digest}"

    def _ensure_base_schema(self, conn: sqlite3.Connection) -> None:
        """创建文档表与索引元数据表。

        Args:
            conn: 当前数据库连接。
        """
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CHUNKS_TABLE} (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                index_name TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(index_name, doc_id)
            )
            """
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS ix_vec_chunks_index ON {_CHUNKS_TABLE}(index_name)"
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_INDEX_META_TABLE} (
                index_name TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    def _ensure_index(self, conn: sqlite3.Connection, index_name: str, dimension: int) -> str:
        """确保索引对应的向量表存在且维度一致。

        Args:
            conn: 当前数据库连接。
            index_name: 业务索引名称。
            dimension: 向量维度。

        Returns:
            向量虚拟表名称。

        Raises:
            ValueError: 已存在索引的维度与当前嵌入模型不一致时抛出。
        """
        table_name = self._table_name(index_name)
        with self._ddl_lock:
            row = conn.execute(
                f"SELECT table_name, dimension FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                (index_name,),
            ).fetchone()
            if row is not None:
                if int(row["dimension"]) != dimension:
                    raise ValueError(
                        f"索引 {index_name} 现有向量维度 {row['dimension']} 与当前嵌入模型 {dimension} 不一致，"
                        "请重建该索引或刷新向量。"
                    )
                return str(row["table_name"])
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} "
                f"USING vec0(embedding float[{dimension}] distance_metric=cosine)"
            )
            conn.execute(
                f"INSERT INTO {_INDEX_META_TABLE}(index_name, table_name, dimension, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (index_name, table_name, dimension, _utc_now()),
            )
            return table_name

    def _index_dimension(self, conn: sqlite3.Connection, index_name: str) -> int | None:
        """读取索引已记录的向量维度。

        Args:
            conn: 当前数据库连接。
            index_name: 业务索引名称。

        Returns:
            已记录的维度；索引尚未创建时返回 None。
        """
        row = conn.execute(
            f"SELECT dimension FROM {_INDEX_META_TABLE} WHERE index_name = ?",
            (index_name,),
        ).fetchone()
        return int(row["dimension"]) if row is not None else None

    def _resolve_dimension(self, embeddings: list[list[float]] | None = None) -> int:
        """确定当前写入使用的向量维度。

        Args:
            embeddings: 本次待写入的向量。

        Returns:
            向量维度。
        """
        if embeddings:
            return len(embeddings[0])
        if self.embedding_dimensions:
            return int(self.embedding_dimensions)
        probe = self.embedding_model.embed_query("dimension probe")
        self.embedding_dimensions = len(probe)
        return len(probe)

    def _row_to_result(self, row: sqlite3.Row, *, score: float | None = None) -> dict[str, Any]:
        """把数据库行转换为统一结果字典。

        Args:
            row: 数据库行。
            score: 可选的相似度或关键词得分。

        Returns:
            含 id、content、metadata 与可选 score 的字典。
        """
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {"raw": metadata}
        metadata = dict(metadata)
        metadata.setdefault("index_name", row["index_name"])
        result: dict[str, Any] = {
            "id": str(row["doc_id"]),
            "content": row["content"],
            "metadata": metadata,
        }
        if score is not None:
            result["score"] = float(score)
        return result

    @staticmethod
    def _matches_filters(
        metadata: dict[str, Any],
        index_name: str,
        filter_conditions: dict[str, Any] | None,
    ) -> bool:
        """判断单条记录是否满足过滤条件。

        Args:
            metadata: 文档元数据。
            index_name: 文档所属索引。
            filter_conditions: 过滤条件，支持 metadata 前缀字段、ne 条件与列表任一匹配。

        Returns:
            是否满足全部条件。
        """
        for field, expected in (filter_conditions or {}).items():
            if field.startswith("metadata."):
                actual = metadata.get(field.split(".", 1)[1])
            elif field == "index_name":
                actual = index_name
            else:
                actual = metadata.get(field)
            if isinstance(expected, dict) and "$ne" in expected:
                if actual is None:
                    continue
                if str(actual).lower() == str(expected["$ne"]).lower():
                    return False
                continue
            if isinstance(expected, list):
                if actual not in expected:
                    return False
                continue
            if actual is None or str(actual).lower() != str(expected).lower():
                return False
        return True

    def _fetch_rows(
        self,
        conn: sqlite3.Connection,
        index_names: list[str],
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[sqlite3.Row]:
        """读取指定索引下的文档行并按过滤条件筛选。

        Args:
            conn: 当前数据库连接。
            index_names: 目标索引名称列表。
            filter_conditions: 过滤条件。

        Returns:
            满足条件的数据库行列表。
        """
        placeholders = ",".join("?" for _ in index_names)
        rows = conn.execute(
            f"SELECT rowid, doc_id, index_name, content, metadata, created_at, updated_at "
            f"FROM {_CHUNKS_TABLE} WHERE index_name IN ({placeholders})",
            index_names,
        ).fetchall()
        if not filter_conditions:
            return list(rows)
        matched: list[sqlite3.Row] = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if self._matches_filters(metadata, row["index_name"], filter_conditions):
                matched.append(row)
        return matched

    def _list_index_names(self) -> list[str]:
        """列出数据库中已有的索引名称。

        Returns:
            索引名称列表。
        """
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            rows = conn.execute(
                f"SELECT DISTINCT index_name FROM {_CHUNKS_TABLE} ORDER BY index_name"
            ).fetchall()
        return [str(row["index_name"]) for row in rows]
    def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        index_name: str | None = None,
    ) -> str:
        """添加一条文档并写入向量。

        Args:
            content: 文档正文。
            metadata: 附加元数据。
            doc_id: 自定义文档 ID。
            index_name: 目标索引名称。

        Returns:
            文档 ID。
        """
        return self.add_batch(
            [{"content": content, "metadata": metadata or {}, "id": doc_id}],
            index_name=index_name,
        )[0]

    def add_batch(
        self,
        documents: list[dict[str, Any]],
        index_name: str | None = None,
    ) -> list[str]:
        """批量写入文档与向量。

        Args:
            documents: 每项包含 content，可选 metadata 与 id。
            index_name: 目标索引名称。

        Returns:
            写入后的文档 ID 列表。
        """
        if not documents:
            return []
        target_index = (index_name or "default").strip() or "default"
        contents = [str(document.get("content", "")) for document in documents]
        embeddings = self.embedding_model.embed_documents(contents)
        dimension = self._resolve_dimension(embeddings)
        now = _utc_now()
        ids: list[str] = []
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            table_name = self._ensure_index(conn, target_index, dimension)
            for position, document in enumerate(documents):
                content = contents[position]
                embedding = embeddings[position]
                doc_id = str(
                    document.get("id")
                    or hashlib.sha1(
                        f"{target_index}:{content}:{now}:{position}".encode("utf-8")
                    ).hexdigest()[:24]
                )
                metadata = dict(document.get("metadata") or {})
                existing = conn.execute(
                    f"SELECT rowid FROM {_CHUNKS_TABLE} WHERE index_name = ? AND doc_id = ?",
                    (target_index, doc_id),
                ).fetchone()
                if existing is not None:
                    rowid = int(existing["rowid"])
                    conn.execute(
                        f"UPDATE {_CHUNKS_TABLE} SET content = ?, metadata = ?, updated_at = ? WHERE rowid = ?",
                        (content, json.dumps(metadata, ensure_ascii=False), now, rowid),
                    )
                    conn.execute(f"DELETE FROM {table_name} WHERE rowid = ?", (rowid,))
                else:
                    cursor = conn.execute(
                        f"INSERT INTO {_CHUNKS_TABLE}(doc_id, index_name, content, metadata, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            doc_id,
                            target_index,
                            content,
                            json.dumps(metadata, ensure_ascii=False),
                            now,
                            now,
                        ),
                    )
                    rowid = int(cursor.lastrowid or 0)
                conn.execute(
                    f"INSERT INTO {table_name}(rowid, embedding) VALUES (?, ?)",
                    (rowid, sqlite_vec.serialize_float32(embedding)),
                )
                ids.append(doc_id)
        return ids

    def update(
        self,
        doc_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        index_name: str | None = None,
    ) -> bool:
        """更新文档正文或元数据，正文变化时重新生成向量。

        Args:
            doc_id: 文档 ID。
            content: 新正文。
            metadata: 新元数据。
            index_name: 目标索引名称。

        Returns:
            是否更新成功。
        """
        target_index = (index_name or "default").strip() or "default"
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            row = conn.execute(
                f"SELECT rowid, content, metadata FROM {_CHUNKS_TABLE} WHERE index_name = ? AND doc_id = ?",
                (target_index, doc_id),
            ).fetchone()
            if row is None:
                return False
            if content is None and metadata is None:
                return False
            next_content = row["content"] if content is None else content
            next_metadata = metadata
            if next_metadata is None:
                try:
                    next_metadata = json.loads(row["metadata"] or "{}")
                except json.JSONDecodeError:
                    next_metadata = {}
            conn.execute(
                f"UPDATE {_CHUNKS_TABLE} SET content = ?, metadata = ?, updated_at = ? WHERE rowid = ?",
                (
                    next_content,
                    json.dumps(next_metadata, ensure_ascii=False),
                    _utc_now(),
                    row["rowid"],
                ),
            )
            if content is not None:
                embedding = self.embedding_model.embed_query(next_content)
                dimension = self._index_dimension(conn, target_index) or self._resolve_dimension(
                    [embedding]
                )
                table_name = self._ensure_index(conn, target_index, dimension)
                conn.execute(f"DELETE FROM {table_name} WHERE rowid = ?", (row["rowid"],))
                conn.execute(
                    f"INSERT INTO {table_name}(rowid, embedding) VALUES (?, ?)",
                    (row["rowid"], sqlite_vec.serialize_float32(embedding)),
                )
        return True

    def delete(self, doc_id: str, index_name: str | None = None) -> bool:
        """删除单篇文档。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名称。

        Returns:
            是否删除成功。
        """
        return self.delete_batch([doc_id], index_name=index_name)[0]

    def delete_batch(self, doc_ids: list[str], index_name: str | None = None) -> list[bool]:
        """批量删除文档。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 目标索引名称。

        Returns:
            与输入顺序一致的成功标记列表。
        """
        if not doc_ids:
            return []
        target_index = (index_name or "default").strip() or "default"
        results = [False] * len(doc_ids)
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            meta_row = conn.execute(
                f"SELECT table_name FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                (target_index,),
            ).fetchone()
            for position, doc_id in enumerate(doc_ids):
                row = conn.execute(
                    f"SELECT rowid FROM {_CHUNKS_TABLE} WHERE index_name = ? AND doc_id = ?",
                    (target_index, str(doc_id)),
                ).fetchone()
                if row is None:
                    continue
                if meta_row is not None:
                    conn.execute(
                        f"DELETE FROM {meta_row['table_name']} WHERE rowid = ?",
                        (row["rowid"],),
                    )
                conn.execute(f"DELETE FROM {_CHUNKS_TABLE} WHERE rowid = ?", (row["rowid"],))
                results[position] = True
        return results

    def delete_by_filter(
        self,
        filter_conditions: dict[str, Any] | None,
        index_names: list[str] | None = None,
    ) -> int:
        """按过滤条件批量删除文档。

        Args:
            filter_conditions: 过滤条件。
            index_names: 目标索引列表。

        Returns:
            删除数量。
        """
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        removed = 0
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            for index_name in targets:
                rows = self._fetch_rows(conn, [index_name], filter_conditions)
                if not rows:
                    continue
                meta_row = conn.execute(
                    f"SELECT table_name FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                    (index_name,),
                ).fetchone()
                rowids = [int(row["rowid"]) for row in rows]
                placeholders = ",".join("?" for _ in rowids)
                if meta_row is not None:
                    conn.execute(
                        f"DELETE FROM {meta_row['table_name']} WHERE rowid IN ({placeholders})",
                        rowids,
                    )
                conn.execute(
                    f"DELETE FROM {_CHUNKS_TABLE} WHERE rowid IN ({placeholders})",
                    rowids,
                )
                removed += len(rowids)
        return removed

    def get(self, doc_id: str, index_name: str | None = None) -> dict[str, Any] | None:
        """按 ID 获取单篇文档。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名称。

        Returns:
            文档结果，不存在时返回 None。
        """
        rows = self.batch_get([doc_id], index_name=index_name)
        return rows[0] if rows else None

    def batch_get(
        self,
        doc_ids: list[str],
        index_name: str | None = None,
    ) -> list[dict[str, Any] | None]:
        """批量获取文档，结果顺序与输入一致。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 目标索引名称。

        Returns:
            文档结果列表。
        """
        if not doc_ids:
            return []
        target_index = (index_name or "default").strip() or "default"
        found: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            placeholders = ",".join("?" for _ in doc_ids)
            rows = conn.execute(
                f"SELECT rowid, doc_id, index_name, content, metadata, created_at, updated_at "
                f"FROM {_CHUNKS_TABLE} WHERE index_name = ? AND doc_id IN ({placeholders})",
                [target_index, *[str(item) for item in doc_ids]],
            ).fetchall()
            for row in rows:
                found[str(row["doc_id"])] = self._row_to_result(row)
        return [found.get(str(doc_id)) for doc_id in doc_ids]

    def exists(self, doc_id: str, index_name: str | None = None) -> bool:
        """检查文档是否存在。

        Args:
            doc_id: 文档 ID。
            index_name: 目标索引名称。

        Returns:
            是否存在。
        """
        return self.get(doc_id, index_name=index_name) is not None

    def count(
        self,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> int:
        """统计符合条件的文档数量。

        Args:
            filter_conditions: 过滤条件。
            index_names: 目标索引列表。

        Returns:
            文档数量。
        """
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        if not targets:
            return 0
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            return len(self._fetch_rows(conn, targets, filter_conditions))
    def search(
        self,
        query: str | None = None,
        k: int = 3,
        filter_conditions: dict[str, Any] | None = None,
        index_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """通用检索：有 query 时走关键词检索，否则按更新时间倒序返回。

        Args:
            query: 检索关键词。
            k: 返回数量。
            filter_conditions: 过滤条件。
            index_names: 目标索引列表。

        Returns:
            检索结果列表。
        """
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        if query:
            return self.keyword_search(
                query,
                k=k,
                index_names=targets or None,
                filter_conditions=filter_conditions,
            )
        if not targets:
            return []
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            rows = self._fetch_rows(conn, targets, filter_conditions)
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        return [self._row_to_result(row) for row in rows[:k]]

    def vector_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        min_similarity: float | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """向量语义检索，按余弦相似度倒序返回。

        Args:
            query: 查询文本。
            k: 返回数量。
            index_names: 目标索引列表。
            min_similarity: 最低相似度。
            filter_conditions: 元数据过滤条件。

        Returns:
            检索结果列表，score 为余弦相似度。
        """
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        if not targets:
            return []
        vector = self.embedding_model.embed_query(query)
        candidates = max(k * 4, 20)
        results: list[dict[str, Any]] = []
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            for index_name in targets:
                dimension = self._index_dimension(conn, index_name)
                if dimension is None or dimension != len(vector):
                    continue
                table_name = self._table_name(index_name)
                rows = conn.execute(
                    f"SELECT c.rowid, c.doc_id, c.index_name, c.content, c.metadata, v.distance "
                    f"FROM {table_name} v JOIN {_CHUNKS_TABLE} c ON c.rowid = v.rowid "
                    f"WHERE v.embedding MATCH ? AND v.k = ?",
                    (sqlite_vec.serialize_float32(vector), candidates),
                ).fetchall()
                for row in rows:
                    result = self._row_to_result(row, score=1.0 - float(row["distance"]))
                    if self._matches_filters(
                        result["metadata"], row["index_name"], filter_conditions
                    ):
                        results.append(result)
        results.sort(key=lambda item: item["score"], reverse=True)
        if min_similarity is not None:
            results = [item for item in results if item["score"] >= min_similarity]
        return results[:k]

    def vector_search_by_ids(
        self, query: str, doc_ids: list[str], index_name: str, k: int
    ) -> list[dict[str, Any]]:
        """在给定文档 ID 范围内做向量检索。

        Args:
            query: 查询文本。
            doc_ids: 候选文档 ID。
            index_name: 索引名称。
            k: 返回数量。

        Returns:
            检索结果列表。
        """
        if not doc_ids:
            return []
        vector = self.embedding_model.embed_query(query)
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            dimension = self._index_dimension(conn, index_name)
            if dimension is None or dimension != len(vector):
                return []
            table_name = self._table_name(index_name)
            placeholders = ",".join("?" for _ in doc_ids)
            rows = conn.execute(
                f"SELECT c.rowid, c.doc_id, c.index_name, c.content, c.metadata, "
                f"vec_distance_cosine(v.embedding, ?) AS distance "
                f"FROM {table_name} v JOIN {_CHUNKS_TABLE} c ON c.rowid = v.rowid "
                f"WHERE c.index_name = ? AND c.doc_id IN ({placeholders})",
                [
                    sqlite_vec.serialize_float32(vector),
                    index_name,
                    *[str(item) for item in doc_ids],
                ],
            ).fetchall()
        results = [
            self._row_to_result(row, score=1.0 - float(row["distance"])) for row in rows
        ]
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:k]

    def list_ids_by_filter(
        self, index_name: str, filter_conditions: dict[str, Any]
    ) -> list[str]:
        """获取索引内满足过滤条件的文档 ID。

        Args:
            index_name: 索引名称。
            filter_conditions: 过滤条件。

        Returns:
            文档 ID 列表。
        """
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            rows = self._fetch_rows(conn, [index_name], filter_conditions)
        return [str(row["doc_id"]) for row in rows]

    def keyword_search(
        self,
        query: str,
        k: int = 3,
        index_names: list[str] | None = None,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """关键词检索，使用子串命中与词频打分。

        Args:
            query: 检索关键词。
            k: 返回数量。
            index_names: 目标索引列表。
            filter_conditions: 元数据过滤条件。

        Returns:
            按分数倒序排列的结果列表。
        """
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        stripped = query.strip()
        if not stripped or not targets:
            return []
        tokens = [token.lower() for token in _TOKEN_PATTERN.findall(stripped)]
        if not tokens:
            tokens = [stripped.lower()]
        scored: list[tuple[float, sqlite3.Row]] = []
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            for row in self._fetch_rows(conn, targets, filter_conditions):
                content = str(row["content"]).lower()
                hits = sum(1 for token in tokens if token in content)
                if hits == 0 and stripped.lower() not in content:
                    continue
                frequency = sum(content.count(token) for token in tokens)
                score = hits * 10.0 + min(frequency, 50) * 0.2
                if stripped.lower() in content:
                    score += 5.0
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._row_to_result(row, score=score) for score, row in scored[:k]]

    def clear_index(self, index_name: str) -> None:
        """清空索引并删除对应向量表。

        Args:
            index_name: 索引名称。
        """
        with self._connect() as conn:
            self._ensure_base_schema(conn)
            row = conn.execute(
                f"SELECT table_name FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                (index_name,),
            ).fetchone()
            if row is not None:
                conn.execute(f"DROP TABLE IF EXISTS {row['table_name']}")
                conn.execute(
                    f"DELETE FROM {_INDEX_META_TABLE} WHERE index_name = ?", (index_name,)
                )
            conn.execute(f"DELETE FROM {_CHUNKS_TABLE} WHERE index_name = ?", (index_name,))

    def refresh_embeddings(
        self,
        new_embedding_model=None,
        *,
        batch_size: int = 50,
        index_names: list[str] | None = None,
    ) -> tuple[int, int]:
        """用新的嵌入模型重算全部向量。

        Args:
            new_embedding_model: 新的嵌入模型实例。
            batch_size: 每批处理的文档数。
            index_names: 目标索引列表。

        Returns:
            成功与失败的数量。
        """
        if new_embedding_model is not None:
            self._embedding_model = new_embedding_model
        targets = self.resolve_index_names(index_names) or self._list_index_names()
        refreshed = 0
        failed = 0
        for index_name in targets:
            with self._connect() as conn:
                self._ensure_base_schema(conn)
                rows = conn.execute(
                    f"SELECT rowid, content FROM {_CHUNKS_TABLE} WHERE index_name = ?",
                    (index_name,),
                ).fetchall()
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                try:
                    embeddings = self.embedding_model.embed_documents(
                        [row["content"] for row in batch]
                    )
                except Exception:  # noqa: BLE001 - 单批失败不影响其余批次
                    failed += len(batch)
                    continue
                with self._connect() as conn:
                    self._ensure_base_schema(conn)
                    old_table = conn.execute(
                        f"SELECT table_name, dimension FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                        (index_name,),
                    ).fetchone()
                    dimension = len(embeddings[0])
                    if old_table is not None and int(old_table["dimension"]) != dimension:
                        conn.execute(f"DROP TABLE IF EXISTS {old_table['table_name']}")
                        conn.execute(
                            f"DELETE FROM {_INDEX_META_TABLE} WHERE index_name = ?",
                            (index_name,),
                        )
                    table_name = self._ensure_index(conn, index_name, dimension)
                    for row, embedding in zip(batch, embeddings, strict=True):
                        conn.execute(
                            f"DELETE FROM {table_name} WHERE rowid = ?", (row["rowid"],)
                        )
                        conn.execute(
                            f"INSERT INTO {table_name}(rowid, embedding) VALUES (?, ?)",
                            (row["rowid"], sqlite_vec.serialize_float32(embedding)),
                        )
                refreshed += len(batch)
        return refreshed, failed
