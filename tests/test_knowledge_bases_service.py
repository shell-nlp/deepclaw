import asyncio

from deepclaw.web_backend.knowledge_bases.service import KnowledgeBaseManager


class FakeMetadataStore:
    def __init__(self):
        self.created_knowledge_base = None
        self.saved_document = None
        self.knowledge_base_source = {
            "knowledge_base_id": "kb001",
            "user_id": "user-1",
            "name": "知识库",
            "description": "",
            "index_prefix": "kb_kb001",
            "passage_index": "kb_kb001_passages",
            "entity_index": "kb_kb001_entities",
            "relation_index": "kb_kb001_relations",
            "document_count": 0,
            "chunk_count": 0,
            "created_at": "2026-06-26T21:00:00+08:00",
            "updated_at": "2026-06-26T21:00:00+08:00",
        }
        self.document_source = {
            "document_id": "doc001",
            "knowledge_base_id": "kb001",
            "user_id": "user-1",
            "file_name": "a.pdf",
            "display_name": "旧名称",
            "content_type": "application/pdf",
            "file_size": 10,
            "chunk_count": 1,
            "storage_path": "demo",
            "created_at": "2026-06-26T21:00:00+08:00",
            "updated_at": "2026-06-26T21:00:00+08:00",
        }

    async def create_knowledge_base(self, source):
        self.created_knowledge_base = source
        return source

    async def get_knowledge_base(self, *, user_id, knowledge_base_id, error_message):
        assert user_id == "user-1"
        assert knowledge_base_id == "kb001"
        return dict(self.knowledge_base_source)

    async def get_document(self, *, user_id, document_id, error_message):
        assert user_id == "user-1"
        assert document_id == "doc001"
        return dict(self.document_source)

    async def save_document(self, *, document_id, source):
        self.saved_document = {"document_id": document_id, "source": dict(source)}
        return source


def test_create_knowledge_base_delegates_metadata_creation():
    async def _run():
        metadata_store = FakeMetadataStore()
        manager = KnowledgeBaseManager(vector_store=object(), metadata_store=metadata_store)

        record = await manager.create_knowledge_base(
            user_id="user-1", name="  测试库  ", description=" desc "
        )

        assert metadata_store.created_knowledge_base is not None
        assert metadata_store.created_knowledge_base["user_id"] == "user-1"
        assert metadata_store.created_knowledge_base["name"] == "测试库"
        assert metadata_store.created_knowledge_base["description"] == "desc"
        assert metadata_store.created_knowledge_base["passage_index"].endswith(
            "_passages"
        )
        assert (
            record.knowledge_base_id
            == metadata_store.created_knowledge_base["knowledge_base_id"]
        )

    asyncio.run(_run())


def test_update_document_delegates_document_metadata_save():
    async def _run():
        metadata_store = FakeMetadataStore()
        manager = KnowledgeBaseManager(vector_store=object(), metadata_store=metadata_store)

        record = await manager.update_document(
            user_id="user-1",
            knowledge_base_id="kb001",
            document_id="doc001",
            display_name="  新名称  ",
        )

        assert metadata_store.saved_document is not None
        assert metadata_store.saved_document["document_id"] == "doc001"
        assert metadata_store.saved_document["source"]["display_name"] == "新名称"
        assert record.display_name == "新名称"

    asyncio.run(_run())
