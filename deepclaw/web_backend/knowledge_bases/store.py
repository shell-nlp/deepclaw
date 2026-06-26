from __future__ import annotations

import os
from typing import Any, Protocol

from elasticsearch import NotFoundError
from sqlmodel import SQLModel, or_, select

from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.constant import home_path
from deepclaw.web_backend.db import build_async_sessionmaker, create_async_engine_from_url
from deepclaw.web_backend.knowledge_bases.models import (
    KnowledgeBaseDocumentMetadata,
    KnowledgeBaseMetadata,
)


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
                        "index_prefix": {"type": "keyword"},
                        "passage_index": {"type": "keyword"},
                        "entity_index": {"type": "keyword"},
                        "relation_index": {"type": "keyword"},
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
        except NotFoundError as exc:
            raise ValueError(error_message) from exc

        source = result["_source"]
        if source.get("user_id") != user_id:
            raise ValueError(error_message)
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
        if db_url is None:
            os.makedirs(home_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(home_path, 'knowledge_bases.db')}"

        self.engine = create_async_engine_from_url(db_url)
        self.async_session = build_async_sessionmaker(self.engine)
        self._init_done = False

    async def _ensure_init(self):
        if self._init_done:
            return
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._init_done = True

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
                raise ValueError(error_message)
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
                raise ValueError(error_message)
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

    @staticmethod
    def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(100, int(page_size)))
        return normalized_page, normalized_page_size
