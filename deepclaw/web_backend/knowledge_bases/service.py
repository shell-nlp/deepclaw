from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from langchain_core.documents import Document
from loguru import logger
from pydantic import BaseModel, Field

from deepclaw.common import create_default_vector_store, create_graph_rag
from deepclaw.common.graph_rag import BaseGraphRAG
from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.text_splitter import PDFParser
from deepclaw.constant import workspace_path
from deepclaw.web_backend.knowledge_bases.store import (
    KnowledgeBaseMetadataStore,
    SQLModelKnowledgeBaseMetadataStore,
)
from deepclaw.utils import get_embedding_model


class KnowledgeBaseRecord(BaseModel):
    knowledge_base_id: str
    user_id: str
    name: str
    description: str = ""
    index_prefix: str
    passage_index: str
    entity_index: str
    relation_index: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: str
    updated_at: str


class KnowledgeBaseDocumentRecord(BaseModel):
    document_id: str
    knowledge_base_id: str
    user_id: str
    file_name: str
    display_name: str
    content_type: str = ""
    file_size: int = 0
    chunk_count: int = 0
    storage_path: str
    created_at: str
    updated_at: str


class KnowledgeBaseDeleteResult(BaseModel):
    knowledge_base: KnowledgeBaseRecord
    deleted_documents: int
    deleted_indexes: dict[str, str]


class KnowledgeBaseUploadError(BaseModel):
    file_name: str
    error: str


class KnowledgeBaseUploadResponse(BaseModel):
    knowledge_base: KnowledgeBaseRecord
    documents: list[KnowledgeBaseDocumentRecord] = Field(default_factory=list)
    errors: list[KnowledgeBaseUploadError] = Field(default_factory=list)


class PaginatedKnowledgeBaseResponse(BaseModel):
    items: list[KnowledgeBaseRecord]
    total: int
    page: int
    page_size: int


class PaginatedKnowledgeBaseDocumentResponse(BaseModel):
    items: list[KnowledgeBaseDocumentRecord]
    total: int
    page: int
    page_size: int


class BulkDeleteKnowledgeBaseResponse(BaseModel):
    deleted_ids: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)


class BulkDeleteDocumentResponse(BaseModel):
    deleted_ids: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)
    knowledge_base: KnowledgeBaseRecord | None = None


class KnowledgeBaseDocumentChunkRecord(BaseModel):
    chunk_id: str
    document_id: str
    segment_id: int | str | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseDocumentDetailResponse(BaseModel):
    knowledge_base: KnowledgeBaseRecord
    document: KnowledgeBaseDocumentRecord
    chunks: list[KnowledgeBaseDocumentChunkRecord] = Field(default_factory=list)
    total_chunks: int
    page: int
    page_size: int


@dataclass(slots=True)
class UploadedKnowledgeFile:
    file_name: str
    content_type: str
    data: bytes


class KnowledgeBaseManager:
    KNOWLEDGE_BASE_INDEX = "rag_knowledge_bases"
    DOCUMENT_INDEX = "rag_knowledge_base_documents"
    STORAGE_ROOT = workspace_path / "pdf_files" / "knowledge_bases"

    def __init__(
        self,
        vector_store: AbstractVectorStore,
        metadata_store: KnowledgeBaseMetadataStore | None = None,
    ):
        self._vector_store = vector_store
        self.metadata_store = metadata_store or SQLModelKnowledgeBaseMetadataStore()

    async def list_knowledge_bases(self, user_id: str) -> list[KnowledgeBaseRecord]:
        return [
            KnowledgeBaseRecord(**item)
            for item in await self.metadata_store.list_knowledge_bases(user_id=user_id)
        ]

    async def search_knowledge_bases(
        self,
        user_id: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedKnowledgeBaseResponse:
        page, page_size = self._normalize_page(page, page_size)
        items, total = await self.metadata_store.search_knowledge_bases(
            user_id=user_id,
            search=search,
            page=page,
            page_size=page_size,
        )
        return PaginatedKnowledgeBaseResponse(
            items=[KnowledgeBaseRecord(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def create_knowledge_base(
        self, user_id: str, name: str, description: str = ""
    ) -> KnowledgeBaseRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Knowledge base name is required.")

        knowledge_base_id = uuid.uuid4().hex
        index_prefix = f"kb_{knowledge_base_id}"
        indexes = BaseGraphRAG.index_names(index_prefix)
        now = self._now()
        source = {
            "knowledge_base_id": knowledge_base_id,
            "user_id": user_id,
            "name": normalized_name,
            "description": description.strip(),
            "index_prefix": index_prefix,
            "passage_index": indexes["passage"],
            "entity_index": indexes["entity"],
            "relation_index": indexes["relation"],
            "document_count": 0,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        created = await self.metadata_store.create_knowledge_base(source)
        return KnowledgeBaseRecord(**created)

    async def get_knowledge_base(
        self, user_id: str, knowledge_base_id: str
    ) -> KnowledgeBaseRecord:
        source = await self.metadata_store.get_knowledge_base(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            error_message="Knowledge base not found.",
        )
        return KnowledgeBaseRecord(**source)

    async def update_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> KnowledgeBaseRecord:
        source = await self.metadata_store.get_knowledge_base(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            error_message="Knowledge base not found.",
        )

        if name is not None:
            normalized_name = name.strip()
            if not normalized_name:
                raise ValueError("Knowledge base name is required.")
            source["name"] = normalized_name
        if description is not None:
            source["description"] = description.strip()
        source["updated_at"] = self._now()

        saved = await self.metadata_store.save_knowledge_base(
            knowledge_base_id=knowledge_base_id,
            source=source,
        )
        return KnowledgeBaseRecord(**saved)

    async def delete_knowledge_base(
        self, user_id: str, knowledge_base_id: str
    ) -> KnowledgeBaseDeleteResult:
        knowledge_base = await self.get_knowledge_base(user_id, knowledge_base_id)
        rag = create_graph_rag(self._vector_store, knowledge_base.index_prefix)
        graph_result = rag.delete_graph(ignore_missing=True)

        document_ids = [
            item.document_id
            for item in await self.list_documents(user_id, knowledge_base_id)
        ]
        if document_ids:
            await self.metadata_store.delete_documents(document_ids=document_ids)

        await self.metadata_store.delete_knowledge_base(knowledge_base_id=knowledge_base_id)

        return KnowledgeBaseDeleteResult(
            knowledge_base=knowledge_base,
            deleted_documents=len(document_ids),
            deleted_indexes=graph_result["result"],
        )

    async def list_documents(
        self, user_id: str, knowledge_base_id: str
    ) -> list[KnowledgeBaseDocumentRecord]:
        await self.get_knowledge_base(user_id, knowledge_base_id)
        return [
            KnowledgeBaseDocumentRecord(**item)
            for item in await self.metadata_store.list_documents(
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
            )
        ]

    async def search_documents(
        self,
        user_id: str,
        knowledge_base_id: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedKnowledgeBaseDocumentResponse:
        await self.get_knowledge_base(user_id, knowledge_base_id)
        page, page_size = self._normalize_page(page, page_size)
        items, total = await self.metadata_store.search_documents(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            search=search,
            page=page,
            page_size=page_size,
        )
        return PaginatedKnowledgeBaseDocumentResponse(
            items=[KnowledgeBaseDocumentRecord(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        *,
        display_name: str,
    ) -> KnowledgeBaseDocumentRecord:
        await self.get_knowledge_base(user_id, knowledge_base_id)
        source = await self.metadata_store.get_document(
            user_id=user_id,
            document_id=document_id,
            error_message="Document not found.",
        )
        if source["knowledge_base_id"] != knowledge_base_id:
            raise ValueError("Document does not belong to this knowledge base.")

        normalized_name = display_name.strip()
        if not normalized_name:
            raise ValueError("Document name is required.")

        source["display_name"] = normalized_name
        source["updated_at"] = self._now()
        saved = await self.metadata_store.save_document(
            document_id=document_id,
            source=source,
        )
        return KnowledgeBaseDocumentRecord(**saved)

    async def get_document_detail(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        *,
        page: int = 1,
        page_size: int = 10,
    ) -> KnowledgeBaseDocumentDetailResponse:
        knowledge_base = await self.get_knowledge_base(user_id, knowledge_base_id)
        document_source = await self.metadata_store.get_document(
            user_id=user_id,
            document_id=document_id,
            error_message="Document not found.",
        )
        if document_source["knowledge_base_id"] != knowledge_base_id:
            raise ValueError("Document does not belong to this knowledge base.")
        document = KnowledgeBaseDocumentRecord(**document_source)

        page, page_size = self._normalize_page(page, page_size)
        hits, total = self._search_with_total(
            index_name=knowledge_base.passage_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"metadata.user_id": user_id}},
                        {"term": {"metadata.knowledge_base_id": knowledge_base_id}},
                        {"term": {"metadata.document_id": document_id}},
                    ]
                }
            },
            size=page_size,
            from_=(page - 1) * page_size,
            sort=[
                {
                    "metadata.segment_id": {
                        "order": "asc",
                        "unmapped_type": "long",
                    }
                }
            ],
        )
        chunks = [
            KnowledgeBaseDocumentChunkRecord(
                chunk_id=hit["_id"],
                document_id=document_id,
                segment_id=hit.get("_source", {}).get("metadata", {}).get("segment_id"),
                content=hit.get("_source", {}).get("content", ""),
                metadata=hit.get("_source", {}).get("metadata", {}),
            )
            for hit in hits
        ]
        return KnowledgeBaseDocumentDetailResponse(
            knowledge_base=knowledge_base,
            document=document,
            chunks=chunks,
            total_chunks=total,
            page=page,
            page_size=page_size,
        )

    async def delete_document(
        self, user_id: str, knowledge_base_id: str, document_id: str
    ) -> dict[str, Any]:
        knowledge_base = await self.get_knowledge_base(user_id, knowledge_base_id)
        source = await self.metadata_store.get_document(
            user_id=user_id,
            document_id=document_id,
            error_message="Document not found.",
        )
        if source["knowledge_base_id"] != knowledge_base_id:
            raise ValueError("Document does not belong to this knowledge base.")

        passage_ids = self._search_ids_by_term(
            index_name=knowledge_base.passage_index,
            field="metadata.file_id",
            value=document_id,
            size=10000,
        )
        rag = create_graph_rag(self._vector_store, knowledge_base.index_prefix)
        delete_result = rag.delete_documents(passage_ids)

        await self.metadata_store.delete_document(document_id=document_id)
        knowledge_base = await self._refresh_knowledge_base_stats(knowledge_base)

        return {
            "knowledge_base": knowledge_base,
            "document_id": document_id,
            "deleted_passages": delete_result["deleted_passages"],
            "deleted_relations": delete_result["deleted_relations"],
            "deleted_entities": delete_result["deleted_entities"],
        }

    async def bulk_delete_knowledge_bases(
        self, user_id: str, knowledge_base_ids: list[str]
    ) -> BulkDeleteKnowledgeBaseResponse:
        deleted_ids: list[str] = []
        failed: dict[str, str] = {}
        for knowledge_base_id in knowledge_base_ids:
            try:
                await self.delete_knowledge_base(user_id, knowledge_base_id)
                deleted_ids.append(knowledge_base_id)
            except Exception as exc:  # noqa: BLE001
                failed[knowledge_base_id] = str(exc)
        return BulkDeleteKnowledgeBaseResponse(
            deleted_ids=deleted_ids,
            failed=failed,
        )

    async def bulk_delete_documents(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_ids: list[str],
    ) -> BulkDeleteDocumentResponse:
        deleted_ids: list[str] = []
        failed: dict[str, str] = {}
        for document_id in document_ids:
            try:
                await self.delete_document(user_id, knowledge_base_id, document_id)
                deleted_ids.append(document_id)
            except Exception as exc:  # noqa: BLE001
                failed[document_id] = str(exc)

        knowledge_base: KnowledgeBaseRecord | None = None
        try:
            knowledge_base = await self.get_knowledge_base(user_id, knowledge_base_id)
        except Exception:  # noqa: BLE001
            knowledge_base = None

        return BulkDeleteDocumentResponse(
            deleted_ids=deleted_ids,
            failed=failed,
            knowledge_base=knowledge_base,
        )

    async def upload_documents(
        self,
        user_id: str,
        knowledge_base_id: str,
        files: Iterable[UploadedKnowledgeFile],
    ) -> KnowledgeBaseUploadResponse:
        knowledge_base = await self.get_knowledge_base(user_id, knowledge_base_id)
        rag = create_graph_rag(self._vector_store, knowledge_base.index_prefix)
        storage_dir = self._storage_dir(user_id, knowledge_base_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        documents: list[KnowledgeBaseDocumentRecord] = []
        errors: list[KnowledgeBaseUploadError] = []

        for uploaded_file in files:
            try:
                document_record = await self._ingest_file(
                    user_id=user_id,
                    knowledge_base=knowledge_base,
                    rag=rag,
                    storage_dir=storage_dir,
                    uploaded_file=uploaded_file,
                )
                documents.append(document_record)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Knowledge file upload failed: {}", uploaded_file.file_name)
                errors.append(
                    KnowledgeBaseUploadError(
                        file_name=uploaded_file.file_name,
                        error=str(exc),
                    )
                )

        knowledge_base = await self._refresh_knowledge_base_stats(knowledge_base)
        return KnowledgeBaseUploadResponse(
            knowledge_base=knowledge_base,
            documents=documents,
            errors=errors,
        )

    async def _ingest_file(
        self,
        *,
        user_id: str,
        knowledge_base: KnowledgeBaseRecord,
        rag: BaseGraphRAG,
        storage_dir: Path,
        uploaded_file: UploadedKnowledgeFile,
    ) -> KnowledgeBaseDocumentRecord:
        original_file_name = Path(uploaded_file.file_name or "unnamed").name
        if not original_file_name:
            raise ValueError("Uploaded file name is required.")

        document_id = uuid.uuid4().hex
        storage_name = f"{document_id}_{self._safe_file_name(original_file_name)}"
        storage_path = storage_dir / storage_name
        storage_path.write_bytes(uploaded_file.data)

        parser = PDFParser(
            bucket_name=self._storage_bucket_name(
                user_id=user_id,
                knowledge_base_id=knowledge_base.knowledge_base_id,
            ),
            file_path=storage_name,
            file_id=document_id,
        )
        chunks = parser.get_chunk()
        prepared_documents = self._prepare_documents(
            knowledge_base=knowledge_base,
            user_id=user_id,
            document_id=document_id,
            storage_name=storage_name,
            storage_path=storage_path,
            original_file_name=original_file_name,
            content_type=uploaded_file.content_type,
            chunks=chunks,
        )

        rag.add_documents(prepared_documents, extract_triplets=True)

        now = self._now()
        source = {
            "document_id": document_id,
            "knowledge_base_id": knowledge_base.knowledge_base_id,
            "user_id": user_id,
            "file_name": original_file_name,
            "display_name": original_file_name,
            "content_type": uploaded_file.content_type or "",
            "file_size": len(uploaded_file.data),
            "chunk_count": len(prepared_documents),
            "storage_path": str(storage_path),
            "created_at": now,
            "updated_at": now,
        }
        saved = await self.metadata_store.save_document(
            document_id=document_id,
            source=source,
        )
        return KnowledgeBaseDocumentRecord(**saved)

    def _prepare_documents(
        self,
        *,
        knowledge_base: KnowledgeBaseRecord,
        user_id: str,
        document_id: str,
        storage_name: str,
        storage_path: Path,
        original_file_name: str,
        content_type: str,
        chunks: list[Document],
    ) -> list[Document]:
        prepared_documents: list[Document] = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = dict(chunk.metadata or {})
            segment_id = metadata.get("segment_id") or index
            # 将管理侧元数据补齐后再交给 RAG 核心索引，避免核心目录承担管理装配职责。
            metadata.update(
                {
                    "user_id": user_id,
                    "knowledge_base_id": knowledge_base.knowledge_base_id,
                    "knowledge_base_name": knowledge_base.name,
                    "document_id": document_id,
                    "file_name": original_file_name,
                    "display_name": original_file_name,
                    "storage_name": storage_name,
                    "storage_path": str(storage_path),
                    "content_type": content_type or "",
                }
            )
            prepared_documents.append(
                Document(
                    id=f"{document_id}_{segment_id}",
                    page_content=chunk.page_content,
                    metadata=metadata,
                )
            )
        return prepared_documents

    async def _refresh_knowledge_base_stats(
        self, knowledge_base: KnowledgeBaseRecord
    ) -> KnowledgeBaseRecord:
        source = await self.metadata_store.get_knowledge_base(
            user_id=knowledge_base.user_id,
            knowledge_base_id=knowledge_base.knowledge_base_id,
            error_message="Knowledge base not found.",
        )
        source["document_count"] = await self.metadata_store.count_documents(
            user_id=knowledge_base.user_id,
            knowledge_base_id=knowledge_base.knowledge_base_id,
        )
        source["chunk_count"] = self._count_index(source["passage_index"])
        source["updated_at"] = self._now()
        saved = await self.metadata_store.save_knowledge_base(
            knowledge_base_id=knowledge_base.knowledge_base_id,
            source=source,
        )
        return KnowledgeBaseRecord(**saved)

    def _search_with_total(
        self,
        *,
        index_name: str,
        query: dict[str, Any],
        size: int,
        from_: int = 0,
        sort: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if isinstance(self._vector_store, ElasticsearchVectorStore):
            es = self._vector_store
            if not es.es_client.indices.exists(index=index_name):
                return [], 0
            body: dict[str, Any] = {
                "query": query,
                "from": from_,
                "track_total_hits": True,
            }
            if sort:
                body["sort"] = sort
            results = es.es_client.search(index=index_name, body=body, size=size)
            total = int(results["hits"]["total"]["value"])
            return results["hits"]["hits"], total

        # PG 分支：将 ES term 查询转为 filter_conditions，手动处理排序和分页
        filter_conditions = self._es_term_query_to_filter(query)
        pg = self._vector_store
        total = pg.count(index_name=index_name, filter_conditions=filter_conditions)
        results = pg.search(
            index_name=index_name,
            filter_conditions=filter_conditions,
            k=from_ + size,
        )
        if sort:
            sort_field = list(sort[0].keys())[0] if sort else ""
            sort_order = sort[0][sort_field]["order"] if sort and sort_field else "asc"
            reverse = sort_order == "desc"
            results.sort(key=lambda r: _safe_sort_key(r, sort_field), reverse=reverse)
        page = results[from_:from_ + size]
        # 归一化为 ES 风格 _id / _source 格式，保持 caller 兼容
        normalized: list[dict[str, Any]] = []
        for r in page:
            normalized.append({
                "_id": r["id"],
                "_source": {
                    "content": r.get("content", ""),
                    "metadata": r.get("metadata", {}),
                },
            })
        return normalized, total

    def _normalize_page(self, page: int, page_size: int) -> tuple[int, int]:
        normalized_page = max(1, int(page))
        normalized_page_size = max(1, min(100, int(page_size)))
        return normalized_page, normalized_page_size

    def _search_ids_by_term(
        self, *, index_name: str, field: str, value: str, size: int
    ) -> list[str]:
        if isinstance(self._vector_store, ElasticsearchVectorStore):
            es = self._vector_store
            if not es.es_client.indices.exists(index=index_name):
                return []
            results = es.es_client.search(
                index=index_name,
                body={"query": {"term": {field: value}}, "_source": False},
                size=size,
            )
            return [hit["_id"] for hit in results["hits"]["hits"]]

        pg = self._vector_store
        results = pg.search(
            index_name=index_name,
            filter_conditions={field: value},
            k=size,
        )
        return [r["id"] for r in results]

    def _count_index(self, index_name: str) -> int:
        if isinstance(self._vector_store, ElasticsearchVectorStore):
            es = self._vector_store
            if not es.es_client.indices.exists(index=index_name):
                return 0
            result = es.es_client.count(
                index=index_name,
                body={"query": {"match_all": {}}},
            )
            return int(result["count"])

        return self._vector_store.count(index_name=index_name)

    def _storage_dir(self, user_id: str, knowledge_base_id: str) -> Path:
        return self.STORAGE_ROOT / self._safe_path_part(user_id) / knowledge_base_id

    def _storage_bucket_name(self, user_id: str, knowledge_base_id: str) -> str:
        return (
            Path("knowledge_bases") / self._safe_path_part(user_id) / knowledge_base_id
        ).as_posix()

    @staticmethod
    def _safe_path_part(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
        return normalized.strip("_") or "default"

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        normalized = re.sub(r"[^\w.\- ]+", "_", file_name.strip())
        normalized = normalized.replace(" ", "_")
        return normalized or "unnamed"

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _es_term_query_to_filter(query: dict[str, Any]) -> dict[str, Any]:
        """将 ES bool/term 查询结构转为扁平 filter_conditions 字典。"""
        filters: dict[str, Any] = {}
        bool_block = query.get("bool", {})
        for clause in bool_block.get("filter", []):
            if "term" in clause:
                for field, value in clause["term"].items():
                    filters[field] = value
        return filters


def _safe_sort_key(result: dict[str, Any], sort_field: str) -> Any:
    """从点分隔的字段路径中提取排序值，兼容 metadata.segment_id 等嵌套路径。"""
    parts = sort_field.split(".")
    value: Any = result
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part, 0)
        else:
            return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return str(value or 0)


embeddings = get_embedding_model()
knowledge_base_manager = KnowledgeBaseManager(
    create_default_vector_store(embedding_model=embeddings)
)

