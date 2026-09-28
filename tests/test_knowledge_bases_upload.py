"""知识库文件上传流程集成测试。

覆盖从 upload_documents → _ingest_file → PDFParser.get_chunk()
→ _prepare_documents → KnowledgeBaseManager._write_passages → add_batch
的完整流水线，包含 PgVectorStore 和 ElasticsearchVectorStore 两种后端。
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

from langchain_core.documents import Document
import pytest

from deepclaw.common.object_storage import LocalObjectStorage
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore
from deepclaw.web_backend.common.errors import BusinessRuleError
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
        self.tasks: dict[str, dict[str, Any]] = {}

    async def save_upload_task(self, source):
        """保存上传任务阶段。

        Args:
            source: 任务元数据。
        """
        self.tasks[source["task_id"]] = deepcopy(source)
        return deepcopy(source)

    async def requeue_upload_tasks(self):
        """模拟后台任务恢复。

        Args:
            无。
        """

    async def touch_upload_task(self, task_id):
        """模拟上传任务心跳。

        Args:
            task_id: 任务 ID。
        """
        return None

    async def claim_upload_task(self, task_id):
        """模拟原子领取排队任务。

        Args:
            task_id: 任务 ID。
        """
        task = self.tasks[task_id]
        if task["status"] != "queued":
            return None
        task["status"] = "parsing"
        return deepcopy(task)

    async def list_upload_tasks(self, *, user_id, knowledge_base_id=None):
        """按用户与知识库查询任务。

        Args:
            user_id: 用户 ID。
            knowledge_base_id: 可选知识库 ID。
        """
        return [deepcopy(task) for task in self.tasks.values()
                if (not user_id or task["user_id"] == user_id)
                and (not knowledge_base_id or task["knowledge_base_id"] == knowledge_base_id)]

    async def delete_upload_tasks(self, *, task_ids):
        """删除指定任务。

        Args:
            task_ids: 任务 ID 列表。
        """
        for task_id in task_ids:
            self.tasks.pop(task_id, None)

    async def retry_upload_task(self, *, task_id, updated_at):
        """把失败任务重新置为排队。

        Args:
            task_id: 任务 ID。
            updated_at: 更新时间。
        """
        task = self.tasks.get(task_id)
        if task is None or task["status"] != "failed":
            return False
        task["status"] = "queued"
        task["error"] = ""
        task["updated_at"] = updated_at
        return True

    async def delete_failed_upload_task(self, *, task_id):
        """删除失败任务记录。

        Args:
            task_id: 任务 ID。
        """
        task = self.tasks.get(task_id)
        if task is None or task["status"] != "failed":
            return False
        self.tasks.pop(task_id, None)
        return True

    async def get_knowledge_base(self, *, user_id, knowledge_base_id, error_message):
        if self._kb_source is None:
            self._kb_source = {
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id,
                "name": "测试知识库",
                "description": "desc",
                "passage_index": f"kb_{knowledge_base_id}_passages",
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
        self.deleted_batches: list[tuple[str, list[str]]] = []
        self.source_ids: list[str] = []
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

    def list_ids_by_filter(self, index_name, filter_conditions):
        """返回预设的来源查询结果。

        Args:
            index_name: 索引名称。
            filter_conditions: 来源过滤条件。
        """
        return list(self.source_ids)

    def delete_batch(self, doc_ids, index_name=None):
        """记录批量删除并返回成功标记。

        Args:
            doc_ids: 待删除文档 ID。
            index_name: 索引名称。
        """
        self.deleted_batches.append((index_name, list(doc_ids)))
        return [True for _ in doc_ids]

    def batch_get(self, doc_ids, index_name=None):
        """模拟空索引中的批量读取。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 索引名称。
        """
        return [None for _ in doc_ids]


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
        """返回不会请求外部服务的固定嵌入模型。"""
        model = MagicMock()
        model.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
        return model

    def list_ids_by_filter(self, index_name, filter_conditions):
        """模拟空索引中的来源查询。

        Args:
            index_name: 索引名称。
            filter_conditions: 来源过滤条件。
        """
        return []

    def batch_get(self, doc_ids, index_name=None):
        """模拟空索引中的批量读取。

        Args:
            doc_ids: 文档 ID 列表。
            index_name: 索引名称。
        """
        return [None for _ in doc_ids]


class FakeObjectStorage:
    """用内存保存对象字节的测试替身。"""

    def __init__(self):
        """初始化空对象集合。"""
        self.objects: dict[tuple[str, str], bytes] = {}
        self.deleted: list[tuple[str, str]] = []

    def get_bytes(self, bucket_name, file_path):
        """读取对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        return self.objects[(bucket_name, file_path)]

    def put_bytes(self, bucket_name, file_path, data, content_type=None):
        """写入对象字节。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
            data: 文件字节。
            content_type: 文件类型。
        """
        del content_type
        self.objects[(bucket_name, file_path)] = data

    def exists(self, bucket_name, file_path):
        """判断对象是否存在。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        return (bucket_name, file_path) in self.objects

    def delete_object(self, bucket_name, file_path):
        """删除对象。

        Args:
            bucket_name: 存储桶名称。
            file_path: 桶内文件路径。
        """
        self.deleted.append((bucket_name, file_path))
        self.objects.pop((bucket_name, file_path), None)


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


def test_background_upload_submission_and_processing(monkeypatch):
    """提交立即返回，后台处理阶段可查询且最终生成文档。"""
    async def scenario():
        """在假解析器和向量存储上执行单文件任务。

        Args:
            无。
        """
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        metadata = FakeMetadataStore()
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(), metadata_store=metadata,
            object_storage=FakeObjectStorage(), upload_workers=1,
        )
        submitted = await manager.submit_uploads("alice", "kb-one", [_UPLOAD_FILE])
        task = submitted.tasks[0]
        assert task.status == "queued"
        assert metadata.saved_document is None
        assert (await manager.list_upload_tasks("alice", "kb-one"))[0].status == "queued"

        await manager._process_upload(metadata.tasks[task.task_id].copy())
        assert metadata.tasks[task.task_id]["status"] == "succeeded"
        assert metadata.saved_document["document_id"] == task.task_id

    asyncio.run(scenario())


def test_failed_upload_task_can_be_retried_and_deleted():
    """失败任务可重试与删除，非失败态一律拒绝。"""
    async def scenario():
        """在假元数据存储上验证重试与删除约束。

        Args:
            无。
        """
        metadata = FakeMetadataStore()
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(), metadata_store=metadata,
            object_storage=FakeObjectStorage(), upload_workers=1,
        )
        submitted = await manager.submit_uploads("alice", "kb-one", [_UPLOAD_FILE])
        task_id = submitted.tasks[0].task_id
        metadata.tasks[task_id].update(status="failed", error="解析失败")

        retried = await manager.retry_upload_task("alice", "kb-one", task_id)
        assert retried.status == "queued"
        assert retried.error == ""

        with pytest.raises(BusinessRuleError):
            await manager.delete_upload_task("alice", "kb-one", task_id)

        metadata.tasks[task_id]["status"] = "failed"
        deleted = await manager.delete_upload_task("alice", "kb-one", task_id)
        assert deleted.task_id == task_id
        assert deleted.deleted is True
        assert metadata.tasks == {}

        with pytest.raises(BusinessRuleError):
            await manager.retry_upload_task("alice", "kb-one", task_id)

    asyncio.run(scenario())


def test_upload_workers_finish_current_file_before_shutdown(monkeypatch):
    """关闭时等待当前任务完成，不再领取排队中的其他文件。"""
    async def scenario():
        """模拟长任务并观察后台 worker 停止时机。

        Args:
            无。
        """
        metadata = FakeMetadataStore()
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(), metadata_store=metadata,
            object_storage=FakeObjectStorage(), upload_workers=1,
        )
        await manager.submit_uploads("alice", "kb-one", [
            _UPLOAD_FILE, UploadedKnowledgeFile("later.pdf", "application/pdf", b"later")
        ])
        started = asyncio.Event()
        release = asyncio.Event()
        processed = []

        async def process(source):
            """模拟一个等待外部完成信号的文件任务。

            Args:
                source: 领取的任务记录。
            """
            processed.append(source["task_id"])
            started.set()
            await release.wait()

        monkeypatch.setattr(manager, "_process_upload", process)
        await manager.start_upload_workers()
        await asyncio.wait_for(started.wait(), 2)
        stopping = asyncio.create_task(manager.stop_upload_workers())
        await asyncio.sleep(0)
        assert not stopping.done()
        release.set()
        await asyncio.wait_for(stopping, 2)
        assert len(processed) == 1

    asyncio.run(scenario())


# ============================ PgVectorStore 后端 ============================


def test_pg_upload_single_file_success(monkeypatch):
    """上传单个文件应成功，返回 1 个文档记录、0 个错误。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
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
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
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


def test_upload_non_pdf_uses_pdf_parser(monkeypatch):
    """TXT/DOCX 等非 PDF 上传也必须经过 PDFParser 转换入口。"""
    async def _run():
        calls = []

        def fake_get_chunk(self):
            """记录解析器类型并返回测试切片。

            Args:
                self: PDFParser 实例。
            """
            calls.append(type(self).__name__)
            return _make_fake_chunks(1)

        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            fake_get_chunk,
        )
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
        )
        result = await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_non_pdf",
            files=[
                UploadedKnowledgeFile("demo.txt", "text/plain", b"hello"),
                UploadedKnowledgeFile(
                    "demo.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    b"fake-docx",
                ),
            ],
        )
        assert len(result.errors) == 0
        assert calls == ["PDFParser", "PDFParser"]

    asyncio.run(_run())


def test_pg_upload_only_writes_passage_index(monkeypatch):
    """图 RAG 移除后，上传只写 passage 索引，不再产生 entity/relation 索引。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        vector_store = FakePgVectorStore()
        manager = KnowledgeBaseManager(
            vector_store=vector_store,
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
        )
        await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_index",
            files=[_UPLOAD_FILE],
        )

        index_names = {batch[1] for batch in vector_store.added_batches}
        assert len(index_names) == 1
        (only_index,) = index_names
        assert only_index.endswith("_passages")

    asyncio.run(_run())


def test_pg_upload_replaces_previous_passages_for_same_document(monkeypatch):
    """同一个 document_id 重新入库时，先清掉旧切片再写新切片。"""
    async def _run():
        """在 FakePgVectorStore 上重复写入同一个来源。

        Args:
            无。
        """
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        vector_store = FakePgVectorStore()
        manager = KnowledgeBaseManager(
            vector_store=vector_store,
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
        )
        knowledge_base = KnowledgeBaseRecord(
            knowledge_base_id="kb_index",
            user_id="user_test",
            name="测试",
            description="",
            passage_index="kb_index_passages",
            created_at="2026-01-01T00:00:00+08:00",
            updated_at="2026-01-01T00:00:00+08:00",
        )
        vector_store.added_batches.append(([{"id": "old"}], "kb_index_passages"))
        vector_store.source_ids = ["old"]

        documents = manager._prepare_documents(
            knowledge_base=knowledge_base,
            user_id="user_test",
            document_id="doc_same",
            bucket_name="knowledge-bases",
            file_path="user_test/kb_index/doc_same_test.pdf",
            storage_name="doc_same_test.pdf",
            storage_path="knowledge-bases/user_test/kb_index/doc_same_test.pdf",
            original_file_name="测试.pdf",
            content_type="application/pdf",
            chunks=_make_fake_chunks(2),
        )
        written = manager._write_passages(
            knowledge_base=knowledge_base, documents=documents
        )

        assert written == 2
        assert vector_store.deleted_batches == [("kb_index_passages", ["old"])]
        assert vector_store.added_batches[-1][1] == "kb_index_passages"

    asyncio.run(_run())


def test_pg_upload_file_error_does_not_block_others(monkeypatch):
    """一个文件失败不应阻塞后续文件的上传。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
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
        object_storage = LocalObjectStorage(tmp_path / "objects")
        manager = KnowledgeBaseManager(
            vector_store=FakePgVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=object_storage,
        )

        await manager.upload_documents(
            user_id="user_test",
            knowledge_base_id="kb_dir",
            files=[_UPLOAD_FILE],
        )

        expected_dir = tmp_path / "objects" / "knowledge-bases" / "user_test" / "kb_dir"
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
        manager = KnowledgeBaseManager(
            vector_store=FakeESVectorStore(),
            metadata_store=FakeMetadataStore(),
            object_storage=FakeObjectStorage(),
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
        object_storage=FakeObjectStorage(),
    )
    chunks = _make_fake_chunks(2)

    kb = MagicMock(knowledge_base_id="kb_001", name="测试库")
    result = manager._prepare_documents(
        knowledge_base=kb,
        user_id="user_1",
        document_id="doc_001",
        bucket_name="knowledge-bases",
        file_path="user_1/kb_001/doc_001_test.pdf",
        storage_name="doc_001_test.pdf",
        storage_path="knowledge-bases/user_1/kb_001/doc_001_test.pdf",
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
        assert meta["bucket_name"] == "knowledge-bases"
        assert meta["file_path"] == "user_1/kb_001/doc_001_test.pdf"
        assert "segment_id" in meta
        assert doc.id is not None


def test_ingest_saves_document_metadata(monkeypatch):
    """_ingest_file 完成后应在 metadata_store 中保存文档记录。"""
    async def _run():
        monkeypatch.setattr(
            "deepclaw.web_backend.knowledge_bases.service.PDFParser.get_chunk",
            lambda self: _make_fake_chunks(2),
        )
        vector_store = FakePgVectorStore()
        metadata_store = FakeMetadataStore()
        object_storage = FakeObjectStorage()
        manager = KnowledgeBaseManager(
            vector_store=vector_store,
            metadata_store=metadata_store,
            object_storage=object_storage,
        )

        kb = KnowledgeBaseRecord(
            knowledge_base_id="kb_test_ingest",
            user_id="user_test",
            name="测试",
            description="",
            passage_index="kb_test_ingest_passages",
            created_at="2026-01-01T00:00:00+08:00",
            updated_at="2026-01-01T00:00:00+08:00",
        )

        record = await manager._ingest_file(
            user_id="user_test",
            knowledge_base=kb,
            uploaded_file=_UPLOAD_FILE,
        )

        assert record.document_id
        assert record.file_name == "测试文档.pdf"
        assert record.chunk_count == 2
        assert metadata_store.saved_document is not None
        assert len(object_storage.objects) == 1
        bucket_name, file_path = next(iter(object_storage.objects))
        assert bucket_name == "knowledge-bases"
        assert file_path.startswith("user_test/kb_test_ingest/")

    asyncio.run(_run())
