import asyncio


def test_sqlmodel_metadata_store_crud_roundtrip():
    async def _run():
        from deepclaw.web_backend.knowledge_bases.store import (
            SQLModelKnowledgeBaseMetadataStore,
        )

        store = SQLModelKnowledgeBaseMetadataStore("sqlite:///:memory:")
        created = await store.create_knowledge_base(
            {
                "knowledge_base_id": "kb001",
                "user_id": "user-1",
                "name": "测试知识库",
                "description": "介绍",
                "index_prefix": "kb_kb001",
                "passage_index": "kb_kb001_passages",
                "entity_index": "kb_kb001_entities",
                "relation_index": "kb_kb001_relations",
                "document_count": 0,
                "chunk_count": 0,
                "created_at": "2026-06-26T22:00:00+08:00",
                "updated_at": "2026-06-26T22:00:00+08:00",
            }
        )

        loaded = await store.get_knowledge_base(
            user_id="user-1",
            knowledge_base_id="kb001",
            error_message="not found",
        )
        items, total = await store.search_knowledge_bases(
            user_id="user-1",
            search="测试",
            page=1,
            page_size=10,
        )

        assert created["knowledge_base_id"] == "kb001"
        assert loaded["name"] == "测试知识库"
        assert total == 1
        assert items[0]["knowledge_base_id"] == "kb001"

    asyncio.run(_run())


def test_sqlmodel_metadata_store_document_crud_and_count():
    async def _run():
        from deepclaw.web_backend.knowledge_bases.store import (
            SQLModelKnowledgeBaseMetadataStore,
        )

        store = SQLModelKnowledgeBaseMetadataStore("sqlite:///:memory:")
        await store.create_knowledge_base(
            {
                "knowledge_base_id": "kb001",
                "user_id": "user-1",
                "name": "测试知识库",
                "description": "",
                "index_prefix": "kb_kb001",
                "passage_index": "kb_kb001_passages",
                "entity_index": "kb_kb001_entities",
                "relation_index": "kb_kb001_relations",
                "document_count": 0,
                "chunk_count": 0,
                "created_at": "2026-06-26T22:00:00+08:00",
                "updated_at": "2026-06-26T22:00:00+08:00",
            }
        )
        await store.save_document(
            document_id="doc001",
            source={
                "document_id": "doc001",
                "knowledge_base_id": "kb001",
                "user_id": "user-1",
                "file_name": "a.pdf",
                "display_name": "文档A",
                "content_type": "application/pdf",
                "file_size": 100,
                "chunk_count": 3,
                "storage_path": "/tmp/a.pdf",
                "created_at": "2026-06-26T22:00:00+08:00",
                "updated_at": "2026-06-26T22:00:00+08:00",
            },
        )

        loaded = await store.get_document(
            user_id="user-1",
            document_id="doc001",
            error_message="not found",
        )
        count = await store.count_documents(user_id="user-1", knowledge_base_id="kb001")
        items, total = await store.search_documents(
            user_id="user-1",
            knowledge_base_id="kb001",
            search="文档",
            page=1,
            page_size=10,
        )

        assert loaded["display_name"] == "文档A"
        assert count == 1
        assert total == 1
        assert items[0]["document_id"] == "doc001"

    asyncio.run(_run())
