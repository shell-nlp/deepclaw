"""知识库文件上传流程集成测试。

覆盖从 upload_documents → _ingest_file → PDFParser.get_chunk()
→ _prepare_documents → BaseGraphRAG.add_documents → _bulk_index
的完整流水线，包含 PgVectorStore 和 ElasticsearchVectorStore 两种后端。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from langchain_core.documents import Document

from deepclaw.common.graph_rag.base import BaseGraphRAG
from deepclaw.common.graph_rag.pg import PgGraphRAG
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore
from deepclaw.web_backend.knowledge_bases.service import (
    KnowledgeBaseManager,
    KnowledgeBaseRecord,
    UploadedKnowledgeFile,
)


# ---------------------------------------------------------------------------
# Fake 存储
# ---------------------------------------------------------------------------

class FakeMetadataStore:
    """记录调用痕迹的元数据存储替身。"""

    def __init__(self):
        self.saved_document = None
        self.document_count = 0
        self._kb_source: dict[str, Any] | None = None
        self._docs: list[dict[str, Any]] = []

    async def get_knowledge_base(self, *, user_id, knowledge_base_id, error_message):
        if self._kb_source is None:
            self._kb_source = {
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id,
                "name": "测试知识库",
                "description": "desc",
                "index_prefix": f"kb_{knowledge_base_id}",
                "passage_index": f"kb_{knowledge_base_id}_passages",
                "entity_index": f"kb_{knowledge_base_id}_entities",
                "relation_index": f"kb_{knowledge_base_id}_relations",
                "document_count": 0,
                "chunk_count": 0,
                "created_at": "2026-01-01T00:00:00+08:00",
                "updated_at": "2026-01-01T00:00:00+08:00",
            }
        return dict(self._kb_source)

    async def save_knowledge_base(self, *, knowledge_base_id, source):
        self._kb_source = dict(source)
        return dict(source)

    async def save_document(self, *, document_id, source):
        self.saved_document = {"document_id": document_id, "source": dict(source)}
        self._docs.append(dict(source))
        return dict(source)

    async def count_documents(self, *, user_id, knowledge_base_id):
        return self.document_count

    async def list_documents(self, *, user_id, knowledge_base_id):
        return list(self._docs)


# ---------------------------------------------------------------------------
# Fake 向量存储
# ---------------------------------------------------------------------------

class FakePgVectorStore(PgVectorStore):
    """不连接真实 PG 的 PgVectorStore 替身，仅记录调用。"""

    def __init__(self):
        super().__init__(
            database_url="postgresql://fake",
            embedding_dimensions=4,
        )
        self.added_batches: list[tuple[list[dict[str, Any]], str]] = []
        self.count_value = 0

    def _connect(self):
        msg = "不应调用真实的 _connect"
        raise RuntimeError(msg)

    def add_batch(self, documents, index_name=None):
        if not documents:
            return []
        self.added_batches.append((documents, index_name))
        return [str(d.get("id", "")) for d in documents]

    def add(self, content, metadata=None, doc_id=None, index_name=None):
        return doc_id or ""

    def count(self, *, index_name=None, index_names=None, filter_conditions=None):
        return self.count_value

    def search(self, *, index_name=None, index_names=None, filter_conditions=None, k=3):
        return []


class FakeESVectorStore(ElasticsearchVectorStore):
    """不连接真实 ES 的 ElasticsearchVectorStore 替身。"""

    def __init__(self):
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        super().__init__(
            url="http://fake:9200",
            username="",
            password="",
        )
        self._es_client = mock_client
        self.added_batches: list[tuple[list[dict[str, Any]], str]] = []

    @property
    def embedding_model(self):
        from deepclaw.utils import get_embedding_model
        return get_embedding_model()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_fake_chunks(count: int = 2) -> list[Document]:
    return [
        Document(
            page_content=f"这是第 {i} 段测试内容。",
            metadata={"segment_id": i, "title": f"标题{i}"},
        )
        for i in range(1, count + 1)
    ]


_UPLOAD_FILE = UploadedKnowledgeFile(
    file_name="测试文档.pdf",
    content_type="application/pdf",
    data=b"fake pdf content",
)


# ============================ PgVectorStore 后端 ============================


def test_pg_upload_single_file_success(monkeypatch):
    """上传单个文件应成功，返回 1 个文档记录、0 个错误。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
        )
        result = await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_test_upload",
            files=[_UPLOAD_FILE],
        )

        assert len(result.documents) == 1
        assert len(result.errors) == 0
        assert result.documents[0].file_name == "测试文档.pdf"
        assert result.documents[0].chunk_count == 2

    asyncio.run(_run())


def test_pg_upload_multiple_files(monkeypatch):
    """上传多个文件应每个生成一条文档记录。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
        )
        result = await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_multi",
            files=[
                UploadedKnowledgeFile(f"doc_{i}.pdf", "application/pdf", b"data")
                for i in range(3)
            ],
        )

        assert len(result.documents) == 3
        assert len(result.errors) == 0
        assert [d.file_name for d in result.documents] == [
            "doc_0.pdf", "doc_1.pdf", "doc_2.pdf"
        ]

    asyncio.run(_run())


def test_pg_upload_calls_add_batch_for_each_index(monkeypatch):
    """上传应调用 add_batch: 每个索引（entity/relation/passage）至少一次。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG,
            "_extract_triplets",
            lambda self, text: [("实体1", "关系", "实体2")],
        )

        vector_store = FakePgVectorStore()
        manager = KnowledgeBaseManager(
            vector_store=vector_store,
            metadata_store=FakeMetadataStore(),
        )
        await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_index",
            files=[_UPLOAD_FILE],
        )

        index_names = {batch[1] for batch in vector_store.added_batches}
        for suffix in ("_entities", "_relations", "_passages"):
            assert any(
                name.endswith(suffix) for name in index_names
            ), f"缺少 {suffix} 索引的写入"

    asyncio.run(_run())


def test_pg_upload_file_error_does_not_block_others(monkeypatch):
    """一个文件失败不应阻塞后续文件的上传。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
        )
        original_ingest = manager._ingest_file

        async def broken_ingest(**kwargs):
            if kwargs["uploaded_file"].file_name == "broken.pdf":
                raise ValueError("模拟解析失败")
            return await original_ingest(**kwargs)

        manager._ingest_file = broken_ingest  # type: ignore[method-assign]

        result = await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_error",
            files=[
                UploadedKnowledgeFile("good.pdf", "application/pdf", b"data"),
                UploadedKnowledgeFile("broken.pdf", "application/pdf", b"data"),
                UploadedKnowledgeFile("also_good.pdf", "application/pdf", b"data"),
            ],
        )

        assert len(result.documents) == 2
        assert len(result.errors) == 1
        assert result.errors[0].file_name == "broken.pdf"

    asyncio.run(_run())


def test_pg_upload_storage_dir_created(monkeypatch, tmp_path):
    """上传应创建存储目录并写入文件。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
        )
        monkeypatch.setattr(manager, "STORAGE_ROOT", tmp_path / "kb_storage")

        await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_dir",
            files=[_UPLOAD_FILE],
        )

        expected_dir = tmp_path / "kb_storage" / "user_test" / "kb_dir"
        assert expected_dir.is_dir()
        stored_files = list(expected_dir.iterdir())
        assert len(stored_files) == 1
        assert stored_files[0].suffix == ".pdf"

    asyncio.run(_run())


# ========================== Elasticsearch 后端 ==========================


def test_es_upload_single_file_success(monkeypatch):
    """ES 后端上传单个文件应成功。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        manager = KnowledgeBaseManager(
            vector_store=FakeESVectorStore(),
            metadata_store=FakeMetadataStore(),
        )
        result = await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_es_test",
            files=[_UPLOAD_FILE],
        )

        assert len(result.documents) == 1
        assert len(result.errors) == 0
        assert result.documents[0].file_name == "测试文档.pdf"

    asyncio.run(_run())


# =========================== 单元辅助测试 ===========================


def test_prepare_documents_adds_metadata():
    """_prepare_documents 应补齐管理侧元数据字段。"""
    manager = KnowledgeBaseManager(
        vector_store=FakePgVectorStore(),
        metadata_store=FakeMetadataStore(),
    )
    chunks = _make_fake_chunks(2)

    kb = MagicMock(knowledge_base_id="kb_001", name="测试库")
    result = manager._prepare_documents(
        knowledge_base=kb,
        user_id="user_1",
        document_id="doc_001",
        storage_name="doc_001_test.pdf",
        storage_path=Path("/fake/doc_001_test.pdf"),
        original_file_name="测试文档.pdf",
        content_type="application/pdf",
        chunks=chunks,
    )

    assert len(result) == 2
    for doc in result:
        meta = doc.metadata
        assert meta["user_id"] == "user_1"
        assert meta["knowledge_base_id"] == "kb_001"
        assert meta["document_id"] == "doc_001"
        assert "segment_id" in meta
        assert doc.id is not None


def test_ingest_saves_document_metadata(monkeypatch):
    """_ingest_file 完成后应在 metadata_store 中保存文档记录。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        monkeypatch.setattr(
            BaseGraphRAG, "_extract_triplets", lambda self, text: []
        )

        vector_store = FakePgVectorStore()
        metadata_store = FakeMetadataStore()
        manager = KnowledgeBaseManager(
            vector_store=vector_store,
            metadata_store=metadata_store,
        )
        rag = PgGraphRAG(vector_store, "kb_test_ingest")

        kb = KnowledgeBaseRecord(
            knowledge_base_id="kb_test_ingest",
            user_id="user_test",
            name="测试",
            description="",
            index_prefix="kb_test_ingest",
            passage_index="kb_test_ingest_passages",
            entity_index="kb_test_ingest_entities",
            relation_index="kb_test_ingest_relations",
            created_at="2026-01-01T00:00:00+08:00",
            updated_at="2026-01-01T00:00:00+08:00",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            record = await manager._ingest_file(
                user_id="user_test",
                knowledge_base=kb,
                rag=rag,
                storage_dir=Path(tmpdir),
                uploaded_file=_UPLOAD_FILE,
            )

        assert record.document_id
        assert record.file_name == "测试文档.pdf"
        assert record.chunk_count == 2
        assert metadata_store.saved_document is not None

    asyncio.run(_run())
