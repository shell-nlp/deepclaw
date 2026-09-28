from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from sqlalchemy import text, update
from sqlmodel import SQLModel, or_, select

from deepclaw.web_backend.common.errors import BusinessRuleError
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.constant import HOME_PATH
from deepclaw.web_backend.db import (
    build_async_sessionmaker,
    create_async_engine_from_url,
    resolve_metadata_db_url,
    should_import_home_sqlite,
)
from deepclaw.web_backend.knowledge_bases.models import (
    KnowledgeBaseDocumentMetadata,
    KnowledgeBaseMetadata,
    KnowledgeUploadTaskMetadata,
)


KNOWLEDGE_BASES_METADATA_IMPORT_MARKER = ".knowledge_bases_imported_to_metadata_db"


def _sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None




def _is_elasticsearch_not_found_error(exc: Exception) -> bool:
    """判断异常是否为 Elasticsearch NotFoundError。

    Args:
        exc: 待判断的异常对象。

    Returns:
        是 Elasticsearch NotFoundError 时返回 True；未安装可选依赖时返回 False。
    """
    try:
        from elasticsearch import NotFoundError
    except ModuleNotFoundError:
        return False
    return isinstance(exc, NotFoundError)


class KnowledgeBaseMetadataStore(Protocol):
    async def list_knowledge_bases(self, *, user_id: str) -> list[dict[str, Any]]: ...

    async def search_knowledge_bases(
        self, *, user_id: str, search: str = "", page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def create_knowledge_base(self, source: dict[str, Any]) -> dict[str, Any]: ...

    async def get_knowledge_base(
        self, *, user_id: str, knowledge_base_id: str, error_message: str
    ) -> dict[str, Any]: ...

    async def save_knowledge_base(
        self, *, knowledge_base_id: str, source: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def delete_knowledge_base(self, *, knowledge_base_id: str) -> None: ...

    async def list_documents(
        self, *, user_id: str, knowledge_base_id: str
    ) -> list[dict[str, Any]]: ...

    async def search_documents(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def get_document(
        self, *, user_id: str, document_id: str, error_message: str
    ) -> dict[str, Any]: ...

    async def save_document(
        self, *, document_id: str, source: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def delete_document(self, *, document_id: str) -> None: ...

    async def delete_documents(self, *, document_ids: list[str]) -> None: ...

    async def count_documents(self, *, user_id: str, knowledge_base_id: str) -> int: ...


class ElasticsearchKnowledgeBaseMetadataStore:
    def __init__(
        self,
        es: ElasticsearchVectorStore,
        *,
        knowledge_base_index: str,
        document_index: str,
    ):
        self.es = es
        self.knowledge_base_index = knowledge_base_index
        self.document_index = document_index
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if not self.es.es_client.indices.exists(index=self.knowledge_base_index):
            self.es.es_client.indices.create(
                index=self.knowledge_base_index,
                mappings={
                    "properties": {
                        "knowledge_base_id": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "name": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}},
                        },
                        "description": {"type": "text"},
                        "passage_index": {"type": "keyword"},
                        "document_count": {"type": "integer"},
                        "chunk_count": {"type": "integer"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                    }
                },
            )

        if not self.es.es_client.indices.exists(index=self.document_index):
            self.es.es_client.indices.create(
                index=self.document_index,
                mappings={
                    "properties": {
                        "document_id": {"type": "keyword"},
                        "knowledge_base_id": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "file_name": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}},
                        },
                        "display_name": {
                            "type": "text",
                            "fields": {"keyword": {"type": "keyword"}},
                        },
                        "content_type": {"type": "keyword"},
                        "file_size": {"type": "long"},
                        "chunk_count": {"type": "integer"},
                        "storage_path": {"type": "keyword"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                    }
                },
            )

        self._initialized = True

    async def list_knowledge_bases(self, *, user_id: str) -> list[dict[str, Any]]:
        return [
            hit["_source"]
            for hit in self._search(
                index_name=self.knowledge_base_index,
                query={"bool": {"filter": [{"term": {"user_id": user_id}}]}},
                size=500,
                sort=[{"updated_at": {"order": "desc"}}],
            )
        ]

    async def search_knowledge_bases(
        self, *, user_id: str, search: str = "", page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int]:
        page, page_size = self._normalize_page(page, page_size)
        hits, total = self._search_with_total(
            index_name=self.knowledge_base_index,
            query=self._build_query(
                filters=[{"term": {"user_id": user_id}}],
                search=search,
                fields=["name^3", "description"],
            ),
            size=page_size,
            from_=(page - 1) * page_size,
            sort=[{"updated_at": {"order": "desc"}}],
        )
        return [hit["_source"] for hit in hits], total

    async def create_knowledge_base(self, source: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        self.es.es_client.index(
            index=self.knowledge_base_index,
            id=source["knowledge_base_id"],
            document=source,
            refresh=True,
        )
        return source

    async def get_knowledge_base(
        self, *, user_id: str, knowledge_base_id: str, error_message: str
    ) -> dict[str, Any]:
        return self._get_owned_document(
            index_name=self.knowledge_base_index,
            document_id=knowledge_base_id,
            user_id=user_id,
            error_message=error_message,
        )

    async def save_knowledge_base(
        self, *, knowledge_base_id: str, source: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_initialized()
        self.es.es_client.index(
            index=self.knowledge_base_index,
            id=knowledge_base_id,
            document=source,
            refresh=True,
        )
        return source

    async def delete_knowledge_base(self, *, knowledge_base_id: str) -> None:
        self._ensure_initialized()
        self.es.es_client.delete(
            index=self.knowledge_base_index,
            id=knowledge_base_id,
            refresh=True,
        )

    async def list_documents(
        self, *, user_id: str, knowledge_base_id: str
    ) -> list[dict[str, Any]]:
        return [
            hit["_source"]
            for hit in self._search(
                index_name=self.document_index,
                query={
                    "bool": {
                        "filter": [
                            {"term": {"user_id": user_id}},
                            {"term": {"knowledge_base_id": knowledge_base_id}},
                        ]
                    }
                },
                size=1000,
                sort=[{"created_at": {"order": "desc"}}],
            )
        ]

    async def search_documents(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        page, page_size = self._normalize_page(page, page_size)
        hits, total = self._search_with_total(
            index_name=self.document_index,
            query=self._build_query(
                filters=[
                    {"term": {"user_id": user_id}},
                    {"term": {"knowledge_base_id": knowledge_base_id}},
                ],
                search=search,
                fields=["display_name^3", "file_name"],
            ),
            size=page_size,
            from_=(page - 1) * page_size,
            sort=[{"created_at": {"order": "desc"}}],
        )
        return [hit["_source"] for hit in hits], total

    async def get_document(
        self, *, user_id: str, document_id: str, error_message: str
    ) -> dict[str, Any]:
        return self._get_owned_document(
            index_name=self.document_index,
            document_id=document_id,
            user_id=user_id,
            error_message=error_message,
        )

    async def save_document(
        self, *, document_id: str, source: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_initialized()
        self.es.es_client.index(
            index=self.document_index,
            id=document_id,
            document=source,
            refresh=True,
        )
        return source

    async def delete_document(self, *, document_id: str) -> None:
        self._ensure_initialized()
        self.es.es_client.delete(
            index=self.document_index,
            id=document_id,
            refresh=True,
        )

    async def delete_documents(self, *, document_ids: list[str]) -> None:
        self._ensure_initialized()
        if not document_ids:
            return
        self.es.es_client.bulk(
            operations=[
                {"delete": {"_index": self.document_index, "_id": document_id}}
                for document_id in document_ids
            ],
            refresh=True,
        )

    async def count_documents(self, *, user_id: str, knowledge_base_id: str) -> int:
        self._ensure_initialized()
        if not self.es.es_client.indices.exists(index=self.document_index):
            return 0
        result = self.es.es_client.count(
            index=self.document_index,
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"user_id": user_id}},
                            {"term": {"knowledge_base_id": knowledge_base_id}},
                        ]
                    }
                }
            },
        )
        return int(result["count"])

    def _get_owned_document(
        self,
        *,
        index_name: str,
        document_id: str,
        user_id: str,
        error_message: str,
    ) -> dict[str, Any]:
        self._ensure_initialized()
        try:
            result = self.es.es_client.get(index=index_name, id=document_id)
        except Exception as exc:
            if _is_elasticsearch_not_found_error(exc):
                raise BusinessRuleError(error_message) from exc
            raise

        source = result["_source"]
        if source.get("user_id") != user_id:
            raise BusinessRuleError(error_message)
        return source

    def _search(
        self,
        *,
        index_name: str,
        query: dict[str, Any],
        size: int,
        sort: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_initialized()
        if not self.es.es_client.indices.exists(index=index_name):
            return []
        body: dict[str, Any] = {"query": query}
        if sort:
            body["sort"] = sort
        results = self.es.es_client.search(index=index_name, body=body, size=size)
        return results["hits"]["hits"]

    def _search_with_total(
        self,
        *,
        index_name: str,
        query: dict[str, Any],
        size: int,
        from_: int = 0,
        sort: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        self._ensure_initialized()
        if not self.es.es_client.indices.exists(index=index_name):
            return [], 0
        body: dict[str, Any] = {
            "query": query,
            "from": from_,
            "track_total_hits": True,
        }
        if sort:
            body["sort"] = sort
        results = self.es.es_client.search(index=index_name, body=body, size=size)
        total = int(results["hits"]["total"]["value"])
        return results["hits"]["hits"], total

    def _build_query(
        self,
        *,
        filters: list[dict[str, Any]],
        search: str,
        fields: list[str],
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"bool": {"filter": filters}}
        normalized_search = search.strip()
        if normalized_search:
            query["bool"]["must"] = [
                {
                    "multi_match": {
                        "query": normalized_search,
                        "fields": fields,
                        "type": "best_fields",
                    }
                }
            ]
        return query

    @staticmethod
    def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(100, int(page_size)))
        return normalized_page, normalized_page_size


class SQLModelKnowledgeBaseMetadataStore:
    def __init__(self, db_url: str | None = None):
        should_import_home_db = db_url is None
        if db_url is None:
            db_url = resolve_metadata_db_url("knowledge_bases.db")

        self.db_url = db_url
        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False
        self._init_lock = None
        self._sqlite_import_path = (
            should_import_home_sqlite(
                filename="knowledge_bases.db",
                target_db_url=self.db_url,
            )
            if should_import_home_db
            else None
        )
        self._sqlite_import_marker = (
            Path(HOME_PATH) / KNOWLEDGE_BASES_METADATA_IMPORT_MARKER
        )

    async def _ensure_init(self):
        if self._init_done:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._init_done:
                return
            async with self.engine.begin() as conn:
                if self.db_url.startswith("postgresql"):
                    await conn.execute(text("SELECT pg_advisory_xact_lock(787017331)"))
                await conn.run_sync(SQLModel.metadata.create_all)
                await self._drop_legacy_graph_columns(conn)
            await self._import_home_sqlite_if_needed()
            self._init_done = True

    async def _drop_legacy_graph_columns(self, conn) -> None:
        """清理图 RAG 时期遗留的 index_prefix / entity_index / relation_index 列。

        Args:
            conn: 当前数据库连接。
        """
        statements = [
            "DROP INDEX IF EXISTS ix_knowledge_bases_entity_index",
            "DROP INDEX IF EXISTS ix_knowledge_bases_relation_index",
            "DROP INDEX IF EXISTS ix_knowledge_bases_index_prefix",
        ]
        if self.db_url.startswith("postgresql"):
            statements.extend(
                [
                    "ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS index_prefix",
                    "ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS entity_index",
                    "ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS relation_index",
                ]
            )
        else:
            # SQLite 不支持 DROP COLUMN IF EXISTS，列不存在时语句会失败，按 best-effort 跳过。
            statements.extend(
                [
                    "ALTER TABLE knowledge_bases DROP COLUMN index_prefix",
                    "ALTER TABLE knowledge_bases DROP COLUMN entity_index",
                    "ALTER TABLE knowledge_bases DROP COLUMN relation_index",
                ]
            )
        for statement in statements:
            try:
                await conn.execute(text(statement))
            except Exception:  # noqa: BLE001
                logger.debug("跳过图 RAG 遗留列清理: {}", statement)

    async def _import_home_sqlite_if_needed(self) -> None:
        if self._sqlite_import_path is None or self._sqlite_import_marker.exists():
            return

        async with self.async_session() as session:
            with sqlite3.connect(self._sqlite_import_path) as connection:
                connection.row_factory = sqlite3.Row
                for table_name, model_class, identity_column in [
                    ("knowledge_bases", KnowledgeBaseMetadata, "knowledge_base_id"),
                    (
                        "knowledge_base_documents",
                        KnowledgeBaseDocumentMetadata,
                        "document_id",
                    ),
                ]:
                    if not _sqlite_table_exists(connection, table_name):
                        continue
                    rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
                    allowed_fields = set(model_class.model_fields)
                    for row in rows:
                        payload = {
                            key: value
                            for key, value in dict(row).items()
                            if key in allowed_fields
                        }
                        result = await session.exec(
                            select(model_class).where(
                                getattr(model_class, identity_column)
                                == payload[identity_column]
                            )
                        )
                        model = result.first()
                        if model is None:
                            model = model_class(**payload)
                        else:
                            for key, value in payload.items():
                                setattr(model, key, value)
                        session.add(model)
                await session.commit()

        self._sqlite_import_marker.write_text("imported\n", encoding="utf-8")

    async def list_knowledge_bases(self, *, user_id: str) -> list[dict[str, Any]]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseMetadata)
                .where(KnowledgeBaseMetadata.user_id == user_id)
                .order_by(KnowledgeBaseMetadata.updated_at.desc())
            )
            return [item.model_dump() for item in result.all()]

    async def search_knowledge_bases(
        self, *, user_id: str, search: str = "", page: int = 1, page_size: int = 10
    ) -> tuple[list[dict[str, Any]], int]:
        await self._ensure_init()
        page, page_size = self._normalize_page(page, page_size)
        statement = select(KnowledgeBaseMetadata).where(
            KnowledgeBaseMetadata.user_id == user_id
        )
        normalized_search = search.strip()
        if normalized_search:
            statement = statement.where(
                or_(
                    KnowledgeBaseMetadata.name.contains(normalized_search),
                    KnowledgeBaseMetadata.description.contains(normalized_search),
                )
            )
        statement = statement.order_by(KnowledgeBaseMetadata.updated_at.desc())
        async with self.async_session() as session:
            result = await session.exec(statement)
            rows = list(result.all())
            total = len(rows)
            items = rows[(page - 1) * page_size : page * page_size]
            return [item.model_dump() for item in items], total

    async def create_knowledge_base(self, source: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_init()
        async with self.async_session() as session:
            model = KnowledgeBaseMetadata(**source)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model.model_dump()

    async def get_knowledge_base(
        self, *, user_id: str, knowledge_base_id: str, error_message: str
    ) -> dict[str, Any]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseMetadata).where(
                    KnowledgeBaseMetadata.knowledge_base_id == knowledge_base_id
                )
            )
            model = result.first()
            if model is None or model.user_id != user_id:
                raise BusinessRuleError(error_message)
            return model.model_dump()

    async def save_knowledge_base(
        self, *, knowledge_base_id: str, source: dict[str, Any]
    ) -> dict[str, Any]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseMetadata).where(
                    KnowledgeBaseMetadata.knowledge_base_id == knowledge_base_id
                )
            )
            model = result.first()
            if model is None:
                model = KnowledgeBaseMetadata(**source)
            else:
                for key, value in source.items():
                    setattr(model, key, value)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model.model_dump()

    async def delete_knowledge_base(self, *, knowledge_base_id: str) -> None:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseMetadata).where(
                    KnowledgeBaseMetadata.knowledge_base_id == knowledge_base_id
                )
            )
            model = result.first()
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def list_documents(
        self, *, user_id: str, knowledge_base_id: str
    ) -> list[dict[str, Any]]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata)
                .where(
                    KnowledgeBaseDocumentMetadata.user_id == user_id,
                    KnowledgeBaseDocumentMetadata.knowledge_base_id == knowledge_base_id,
                )
                .order_by(KnowledgeBaseDocumentMetadata.created_at.desc())
            )
            return [item.model_dump() for item in result.all()]

    async def search_documents(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:
        await self._ensure_init()
        page, page_size = self._normalize_page(page, page_size)
        statement = select(KnowledgeBaseDocumentMetadata).where(
            KnowledgeBaseDocumentMetadata.user_id == user_id,
            KnowledgeBaseDocumentMetadata.knowledge_base_id == knowledge_base_id,
        )
        normalized_search = search.strip()
        if normalized_search:
            statement = statement.where(
                or_(
                    KnowledgeBaseDocumentMetadata.display_name.contains(
                        normalized_search
                    ),
                    KnowledgeBaseDocumentMetadata.file_name.contains(normalized_search),
                )
            )
        statement = statement.order_by(KnowledgeBaseDocumentMetadata.created_at.desc())
        async with self.async_session() as session:
            result = await session.exec(statement)
            rows = list(result.all())
            total = len(rows)
            items = rows[(page - 1) * page_size : page * page_size]
            return [item.model_dump() for item in items], total

    async def get_document(
        self, *, user_id: str, document_id: str, error_message: str
    ) -> dict[str, Any]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata).where(
                    KnowledgeBaseDocumentMetadata.document_id == document_id
                )
            )
            model = result.first()
            if model is None or model.user_id != user_id:
                raise BusinessRuleError(error_message)
            return model.model_dump()

    async def save_document(
        self, *, document_id: str, source: dict[str, Any]
    ) -> dict[str, Any]:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata).where(
                    KnowledgeBaseDocumentMetadata.document_id == document_id
                )
            )
            model = result.first()
            if model is None:
                model = KnowledgeBaseDocumentMetadata(**source)
            else:
                for key, value in source.items():
                    setattr(model, key, value)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model.model_dump()

    async def delete_document(self, *, document_id: str) -> None:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata).where(
                    KnowledgeBaseDocumentMetadata.document_id == document_id
                )
            )
            model = result.first()
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def delete_documents(self, *, document_ids: list[str]) -> None:
        await self._ensure_init()
        if not document_ids:
            return
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata).where(
                    KnowledgeBaseDocumentMetadata.document_id.in_(document_ids)
                )
            )
            rows = list(result.all())
            for row in rows:
                await session.delete(row)
            await session.commit()

    async def count_documents(self, *, user_id: str, knowledge_base_id: str) -> int:
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeBaseDocumentMetadata).where(
                    KnowledgeBaseDocumentMetadata.user_id == user_id,
                    KnowledgeBaseDocumentMetadata.knowledge_base_id == knowledge_base_id,
                )
            )
            return len(list(result.all()))

    async def save_upload_task(self, source: dict[str, Any]) -> dict[str, Any]:
        """创建或更新上传任务。

        Args:
            source: 完整的任务字段。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            if source["status"] != "queued":
                allowed_statuses = {
                    "parsing": ["parsing"],
                    "indexing": ["parsing", "indexing"],
                    "succeeded": ["indexing"],
                    "failed": ["parsing", "indexing"],
                }[source["status"]]
                result = await session.exec(
                    update(KnowledgeUploadTaskMetadata)
                    .where(
                        KnowledgeUploadTaskMetadata.task_id == source["task_id"],
                        KnowledgeUploadTaskMetadata.status.in_(allowed_statuses),
                    )
                    .values(**{
                        key: value for key, value in source.items()
                        if key not in {"task_id", "created_at"}
                    })
                )
                await session.commit()
                if result.rowcount != 1:
                    raise RuntimeError("上传任务已被其他进程接管或终止")
                row = await session.exec(
                    select(KnowledgeUploadTaskMetadata).where(
                        KnowledgeUploadTaskMetadata.task_id == source["task_id"]
                    )
                )
                return row.one().model_dump()
            result = await session.exec(
                select(KnowledgeUploadTaskMetadata).where(
                    KnowledgeUploadTaskMetadata.task_id == source["task_id"]
                )
            )
            model = result.first()
            if model is None:
                model = KnowledgeUploadTaskMetadata(**source)
            else:
                for key, value in source.items():
                    setattr(model, key, value)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model.model_dump()

    async def claim_upload_task(self, task_id: str) -> dict[str, Any] | None:
        """原子领取待处理任务，避免多 worker 重复执行。

        Args:
            task_id: 待领取任务 ID。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                update(KnowledgeUploadTaskMetadata)
                .where(
                    KnowledgeUploadTaskMetadata.task_id == task_id,
                    KnowledgeUploadTaskMetadata.status == "queued",
                )
                .values(status="parsing", updated_at=datetime.now().astimezone().isoformat())
            )
            if result.rowcount != 1:
                await session.commit()
                return None
            claimed = await session.exec(
                select(KnowledgeUploadTaskMetadata).where(
                    KnowledgeUploadTaskMetadata.task_id == task_id
                )
            )
            row = claimed.one().model_dump()
            await session.commit()
            return row

    async def requeue_upload_tasks(self) -> None:
        """恢复超过十分钟无更新的中断任务，避免抢占活跃实例。

        Args:
            无。
        """
        await self._ensure_init()
        stale_before = (datetime.now().astimezone() - timedelta(minutes=10)).isoformat()
        async with self.async_session() as session:
            await session.exec(
                update(KnowledgeUploadTaskMetadata)
                .where(
                    KnowledgeUploadTaskMetadata.status.in_(["parsing", "indexing"]),
                    KnowledgeUploadTaskMetadata.updated_at < stale_before,
                )
                .values(status="queued")
            )
            await session.commit()

    async def touch_upload_task(self, task_id: str) -> None:
        """更新运行中任务心跳，防止被其他实例误判为过期。

        Args:
            task_id: 正在执行的任务 ID。
        """
        await self._ensure_init()
        async with self.async_session() as session:
            await session.exec(
                update(KnowledgeUploadTaskMetadata)
                .where(
                    KnowledgeUploadTaskMetadata.task_id == task_id,
                    KnowledgeUploadTaskMetadata.status.in_(["parsing", "indexing"]),
                )
                .values(updated_at=datetime.now().astimezone().isoformat())
            )
            await session.commit()

    async def list_upload_tasks(
        self, *, user_id: str, knowledge_base_id: str | None = None
    ) -> list[dict[str, Any]]:
        """列出用户上传任务，供前端轮询和后台恢复。

        Args:
            user_id: 归属用户；空字符串表示后台读取全部。
            knowledge_base_id: 可选知识库过滤。
        """
        await self._ensure_init()
        statement = select(KnowledgeUploadTaskMetadata)
        if user_id:
            statement = statement.where(KnowledgeUploadTaskMetadata.user_id == user_id)
        if knowledge_base_id:
            statement = statement.where(
                KnowledgeUploadTaskMetadata.knowledge_base_id == knowledge_base_id
            )
        async with self.async_session() as session:
            result = await session.exec(
                statement.order_by(KnowledgeUploadTaskMetadata.created_at.desc())
            )
            rows = list(result.all())
            if user_id:
                rows = rows[:100]
            return [item.model_dump() for item in rows]

    async def delete_upload_tasks(self, *, task_ids: list[str]) -> None:
        """删除上传任务记录。

        Args:
            task_ids: 待删除任务 ID。
        """
        if not task_ids:
            return
        await self._ensure_init()
        async with self.async_session() as session:
            result = await session.exec(
                select(KnowledgeUploadTaskMetadata).where(
                    KnowledgeUploadTaskMetadata.task_id.in_(task_ids)
                )
            )
            for row in result.all():
                await session.delete(row)
            await session.commit()

    @staticmethod
    def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(100, int(page_size)))
        return normalized_page, normalized_page_size
