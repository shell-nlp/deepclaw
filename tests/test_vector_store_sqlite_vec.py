from pathlib import Path

import pytest

from deepclaw.common.vector_store.sqlite_vec import SqliteVecVectorStore


class FakeEmbeddingModel:
    """把文本映射到固定维度向量，避免测试依赖真实嵌入服务。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        return [
            1.0 if "苹果" in lowered else 0.0,
            1.0 if "香蕉" in lowered else 0.0,
            0.1,
        ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """返回批量文本向量。"""
        self.calls.extend(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """返回查询文本向量。"""
        self.calls.append(text)
        return self._vector(text)


@pytest.fixture()
def store(tmp_path: Path) -> SqliteVecVectorStore:
    """创建使用临时数据库的向量库实例。"""
    return SqliteVecVectorStore(tmp_path / "vector.db", embedding_model=FakeEmbeddingModel())


def test_add_and_vector_search_returns_similarity(store: SqliteVecVectorStore):
    """验证写入后可按余弦相似度检索到最接近的切片。"""

    ids = store.add_batch(
        [
            {"content": "苹果是一种水果", "metadata": {"document_id": "d1", "segment_id": 1}},
            {"content": "香蕉是一种水果", "metadata": {"document_id": "d1", "segment_id": 2}},
        ],
        index_name="kb_demo",
    )

    hits = store.vector_search("苹果", k=2, index_names=["kb_demo"])

    assert len(hits) == 2
    assert hits[0]["id"] == ids[0]
    assert hits[0]["score"] > hits[1]["score"]
    assert hits[0]["metadata"]["index_name"] == "kb_demo"


def test_keyword_search_matches_chinese_substring(store: SqliteVecVectorStore):
    """验证中文关键词无需分词即可命中。"""

    store.add_batch(
        [{"content": "番茄炒蛋的做法", "metadata": {"document_id": "d2"}}],
        index_name="kb_demo",
    )

    hits = store.keyword_search("番茄", k=3, index_names=["kb_demo"])

    assert len(hits) == 1
    assert "番茄" in hits[0]["content"]


def test_filters_support_ne_and_list(store: SqliteVecVectorStore):
    """验证元数据过滤支持不等值条件与列表任一匹配。"""

    store.add_batch(
        [
            {"content": "启用的切片", "metadata": {"document_id": "d1", "state": True}},
            {"content": "停用的切片", "metadata": {"document_id": "d2", "state": False}},
        ],
        index_name="kb_demo",
    )

    visible = store.search(
        k=10,
        index_names=["kb_demo"],
        filter_conditions={"metadata.state": {"$ne": False}},
    )
    by_ids = store.list_ids_by_filter("kb_demo", {"metadata.state": {"$ne": False}})

    assert [hit["content"] for hit in visible] == ["启用的切片"]
    assert len(by_ids) == 1


def test_delete_and_clear_index(store: SqliteVecVectorStore):
    """验证删除文档与清空索引的行为。"""

    ids = store.add_batch(
        [
            {"content": "第一段", "metadata": {"document_id": "d1"}},
            {"content": "第二段", "metadata": {"document_id": "d2"}},
        ],
        index_name="kb_demo",
    )

    assert store.delete(ids[0], index_name="kb_demo") is True
    assert store.count(index_names=["kb_demo"]) == 1

    store.clear_index("kb_demo")

    assert store.count(index_names=["kb_demo"]) == 0
    assert store.vector_search("第一段", k=3, index_names=["kb_demo"]) == []


def test_delete_by_filter_removes_document(store: SqliteVecVectorStore):
    """验证按文档 ID 批量清理切片。"""

    store.add_batch(
        [
            {"content": "a", "metadata": {"document_id": "doc-1"}},
            {"content": "b", "metadata": {"document_id": "doc-1"}},
            {"content": "c", "metadata": {"document_id": "doc-2"}},
        ],
        index_name="kb_demo",
    )

    removed = store.delete_by_filter({"metadata.document_id": "doc-1"}, ["kb_demo"])

    assert removed == 2
    assert store.count(index_names=["kb_demo"]) == 1
