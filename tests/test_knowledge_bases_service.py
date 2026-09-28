import asyncio

from deepclaw.web_backend.knowledge_bases.service import KnowledgeBaseManager


class FakePassageStore:
    """模拟 PgVectorStore.search 的替身：按更新时间倒序返回前 k 条。"""

    def __init__(self, segments):
        """按给定 segment_id 顺序构造切片。

        Args:
            segments: segment_id 序列，越靠后表示写入越晚。
        """
        self.rows = [
            {
                "id": f"doc001_{segment}",
                "content": f"内容{segment}",
                "metadata": {"document_id": "doc001", "segment_id": segment},
            }
            for segment in segments
        ]

    def count(self, *, index_name=None, index_names=None, filter_conditions=None):
        """返回命中总数。

        Args:
            index_name: 单个索引名。
            index_names: 索引名列表。
            filter_conditions: 过滤条件。
        """
        return len(self.rows)

    def search(self, *, index_name=None, index_names=None, filter_conditions=None, k=3):
        """模拟 PG 的 ORDER BY updated_at DESC + LIMIT。

        Args:
            index_name: 单个索引名。
            index_names: 索引名列表。
            filter_conditions: 过滤条件。
            k: 返回数量上限。
        """
        return list(reversed(self.rows))[:k]

    def batch_get(self, ids, *, index_name=None):
        """按 ID 返回切片副本。

        Args:
            ids: 目标切片 ID 列表。
            index_name: 索引名。
        """
        wanted = set(ids)
        return [dict(row) for row in self.rows if row["id"] in wanted]

    def update(self, doc_id, content=None, metadata=None, index_name=None):
        """就地更新切片的正文与元数据。

        Args:
            doc_id: 切片 ID。
            content: 新正文，None 表示不修改。
            metadata: 新元数据，None 表示不修改。
            index_name: 索引名。
        """
        for row in self.rows:
            if row["id"] != doc_id:
                continue
            if content is not None:
                row["content"] = content
            if metadata is not None:
                row["metadata"] = dict(metadata)
            return True
        return False


class FakeMetadataStore:
    def __init__(self):
        self.created_knowledge_base = None
        self.saved_document = None
        self.knowledge_base_source = {
            "knowledge_base_id": "kb001",
            "user_id": "user-1",
            "name": "知识库",
            "description": "",
            "passage_index": "kb_kb001_passages",
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


def test_document_chunk_pagination_sorts_full_result_before_slicing():
    """PG 分页必须先取回命中全集再排序，保证第一页从 segment_id = 1 开始。"""
    async def _run():
        """在假 PG 向量库上校验切片排序与分页。

        Args:
            无。
        """
        manager = KnowledgeBaseManager(
            vector_store=FakePassageStore(range(1, 21)),
            metadata_store=FakeMetadataStore(),
        )
        query = {"bool": {"filter": [{"term": {"metadata.document_id": "doc001"}}]}}
        sort = [{"metadata.segment_id": {"order": "asc"}}]

        first_page, total = manager._search_with_total(
            index_name="kb_kb001_passages", query=query, size=8, from_=0, sort=sort
        )
        second_page, _ = manager._search_with_total(
            index_name="kb_kb001_passages", query=query, size=8, from_=8, sort=sort
        )

        assert total == 20
        assert [
            hit["_source"]["metadata"]["segment_id"] for hit in first_page
        ] == list(range(1, 9))
        assert [
            hit["_source"]["metadata"]["segment_id"] for hit in second_page
        ] == list(range(9, 17))

    asyncio.run(_run())


def test_update_document_chunk_updates_state_and_content():
    """更新切片应同时写入新正文与开关状态，并保留原有元数据。"""

    async def _run():
        """在假向量库上校验切片更新结果。

        Args:
            无。
        """
        store = FakePassageStore([1])
        manager = KnowledgeBaseManager(
            vector_store=store, metadata_store=FakeMetadataStore()
        )

        record = await manager.update_document_chunk(
            user_id="user-1",
            knowledge_base_id="kb001",
            document_id="doc001",
            chunk_id="doc001_1",
            content="新正文",
            state=False,
        )

        assert record.chunk_id == "doc001_1"
        assert record.content == "新正文"
        assert record.metadata["state"] is False
        assert store.rows[0]["content"] == "新正文"
        assert store.rows[0]["metadata"]["state"] is False
        assert store.rows[0]["metadata"]["segment_id"] == 1

    asyncio.run(_run())
