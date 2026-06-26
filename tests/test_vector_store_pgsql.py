import pytest

from deepclaw.common.vector_store.pgsql import PgVectorStore


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


def test_keyword_search_rejects_conflicting_index_arguments():
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )
    with pytest.raises(ValueError, match="index_name and index_names"):
        store.keyword_search("hello", index_name="kb_a", index_names=["kb_b"])


def test_partition_table_name_is_stable():
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )
    assert store._partition_table_name("kb-demo") == "vector_store_documents_kb_demo"


def test_keyword_search_merges_multiple_indexes(monkeypatch):
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )

    recorded = {}

    def fake_fetch_keyword_rows(*, query, index_names, limit):
        recorded["query"] = query
        recorded["index_names"] = index_names
        recorded["limit"] = limit
        return [
            {"id": "1", "content": "alpha", "metadata": {"index_name": "kb_a"}, "score": 0.7},
            {"id": "2", "content": "beta", "metadata": {"index_name": "kb_b"}, "score": 0.6},
        ]

    monkeypatch.setattr(store, "_fetch_keyword_rows", fake_fetch_keyword_rows)

    results = store.keyword_search("hello", k=2, index_names=["kb_a", "kb_b"])

    assert recorded == {"query": "hello", "index_names": ["kb_a", "kb_b"], "limit": 2}
    assert [item["content"] for item in results] == ["alpha", "beta"]


def test_vector_search_merges_partition_candidates(monkeypatch):
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )

    requested_indexes = []

    def fake_fetch_vector_candidates(*, index_name, query_vector, limit):
        requested_indexes.append((index_name, query_vector, limit))
        data = {
            "kb_a": [
                {"id": "a1", "content": "alpha", "metadata": {"index_name": "kb_a"}, "score": 0.91},
            ],
            "kb_b": [
                {"id": "b1", "content": "beta", "metadata": {"index_name": "kb_b"}, "score": 0.87},
            ],
        }
        return data[index_name]

    monkeypatch.setattr(store, "_fetch_vector_candidates", fake_fetch_vector_candidates)

    results = store.vector_search("hello", k=2, index_names=["kb_a", "kb_b"])

    assert requested_indexes == [
        ("kb_a", [0.1, 0.2, 0.3], 8),
        ("kb_b", [0.1, 0.2, 0.3], 8),
    ]
    assert [item["content"] for item in results] == ["alpha", "beta"]
