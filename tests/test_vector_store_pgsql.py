import pytest

from deepclaw.common.vector_store.pgsql import PgVectorStore


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


def _make_mock_connect(table_exists: bool, existing_dim: int | None = None):
    """返回一个 mock _connect 工厂，用于捕获 execute 的 SQL。"""
    executed = []

    class MockCursor:
        def __init__(self):
            self.rowcount = 0

        def execute(self, sql, params=None):
            executed.append(sql)

        def fetchone(self):
            if "information_schema.tables" in executed[-1]:
                return {"exists": table_exists}
            if "pg_catalog.pg_attribute" in executed[-1]:
                return {"atttypmod": existing_dim + 4} if existing_dim is not None else None
            return None

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class MockConnection:
        def cursor(self):
            return MockCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return executed, MockConnection


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


def test_ensure_base_schema_detects_dimension_mismatch():
    """当已有表向量维度和当前请求不一致时，应发送 ALTER TABLE 修正。"""
    executed, mock_conn = _make_mock_connect(table_exists=True, existing_dim=1536)
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=1024,
    )
    store._connect = lambda: mock_conn()
    store._ensure_base_schema()

    alter_sent = any("ALTER" in sql and "embedding" in sql for sql in executed)
    assert alter_sent, "维度不匹配时应发送 ALTER TABLE 修正 embedding 列"


def test_ensure_base_schema_skips_alter_on_matching_dimension():
    """当已有表向量维度匹配时，不应发送 ALTER TABLE。"""
    executed, mock_conn = _make_mock_connect(table_exists=True, existing_dim=1024)
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=1024,
    )
    store._connect = lambda: mock_conn()
    store._ensure_base_schema()

    alter_sent = any("ALTER" in sql and "embedding" in sql for sql in executed)
    assert not alter_sent, "维度匹配时不应发送 ALTER TABLE"


def test_ensure_base_schema_creates_table_when_not_exists():
    """当表不存在时应正常创建，不检查已有维度。"""
    executed, mock_conn = _make_mock_connect(table_exists=False)
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=768,
    )
    store._connect = lambda: mock_conn()
    store._ensure_base_schema()

    create_sent = any("CREATE TABLE" in sql for sql in executed)
    assert create_sent, "表不存在时应发送 CREATE TABLE"


def test_vector_search_merges_partition_candidates(monkeypatch):
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )

    requested_indexes = []

    def fake_fetch_vector_candidates(*, index_name, query_vector, limit, filter_conditions=None):
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
