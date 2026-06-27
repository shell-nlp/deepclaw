import asyncio
from types import SimpleNamespace


def test_sqlmodel_metadata_store_defaults_to_pg_database_url_when_configured(monkeypatch):
    import deepclaw.web_backend.db as db_module
    import deepclaw.web_backend.knowledge_bases.store as kb_store_module

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        db_module,
        "settings",
        SimpleNamespace(
            PG_DATABASE_URL="postgresql://admin:admin@localhost:55432/deepclaw"
        ),
    )
    monkeypatch.setattr(
        kb_store_module,
        "create_async_engine_from_url",
        lambda db_url: captured.setdefault("db_url", db_url) or object(),
    )
    monkeypatch.setattr(
        kb_store_module,
        "build_async_sessionmaker",
        lambda engine: captured.setdefault("engine", engine) or object(),
    )

    kb_store_module.SQLModelKnowledgeBaseMetadataStore()

    assert captured["db_url"] == "postgresql://admin:admin@localhost:55432/deepclaw"


def test_sqlmodel_metadata_store_imports_existing_home_sqlite_data(tmp_path, monkeypatch):
    async def _run():
        import deepclaw.web_backend.db as db_module
        import deepclaw.web_backend.knowledge_bases.store as kb_store_module

        monkeypatch.setattr(db_module, "home_path", tmp_path)
        monkeypatch.setattr(
            db_module,
            "settings",
            SimpleNamespace(PG_DATABASE_URL=f"sqlite:///{tmp_path / 'metadata.db'}"),
        )
        monkeypatch.setattr(kb_store_module, "home_path", tmp_path)

        legacy_store = kb_store_module.SQLModelKnowledgeBaseMetadataStore(
            f"sqlite:///{tmp_path / 'knowledge_bases.db'}"
        )
        await legacy_store.create_knowledge_base(
            {
                "knowledge_base_id": "kb-legacy",
                "user_id": "user-1",
                "name": "刘宇的知识",
                "description": "legacy",
                "index_prefix": "kb_legacy",
                "passage_index": "kb_legacy_passages",
                "entity_index": "kb_legacy_entities",
                "relation_index": "kb_legacy_relations",
                "document_count": 0,
                "chunk_count": 0,
                "created_at": "2026-06-26T22:00:00+08:00",
                "updated_at": "2026-06-26T22:00:00+08:00",
            }
        )

        store = kb_store_module.SQLModelKnowledgeBaseMetadataStore()
        loaded = await store.get_knowledge_base(
            user_id="user-1",
            knowledge_base_id="kb-legacy",
            error_message="not found",
        )

        assert loaded["name"] == "刘宇的知识"

    asyncio.run(_run())


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
