
from deepclaw.common.vector_store.elasticsearch import build_es_filter_clauses
from deepclaw.common.vector_store.pgsql import PgVectorStore
from pgvector import Vector


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


def test_metadata_filter_ne_excludes_only_explicit_value():
    """不等值过滤应写成 IS DISTINCT FROM，缺失字段因此不会被排除。"""
    params: dict[str, object] = {}

    clauses = PgVectorStore._build_filter_clauses(
        {"metadata.state": {"$ne": False}, "metadata.document_id": "doc001"},
        params,
        prefix="filter",
    )

    assert clauses[0] == "metadata ->> 'state' IS DISTINCT FROM %(filter_0)s"
    assert params["filter_0"] == "false"
    assert clauses[1] == "metadata ->> 'document_id' = %(filter_1)s"
    assert params["filter_1"] == "doc001"


def test_index_object_names_stay_within_postgres_limit():
    """索引对象名必须短于 63 字符，避免被截断成与分区表同名而跳过创建。"""
    long_index = f"kb_{'a' * 32}_passages"
    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=1024,
    )

    names = [
        store._index_object_name(long_index, "id_uidx"),
        store._bm25_index_name(long_index),
        store._vector_index_name(long_index),
        store._search_vector_index_name(long_index),
    ]

    assert all(len(name) < 63 for name in names)
    assert len(set(names)) == len(names)
    assert store._partition_table_name(long_index) not in names


def test_matches_ne_filters_treats_missing_as_enabled():
    """Python 侧不等值过滤与 SQL 语义一致：缺字段放行，显式停用才拦截。"""
    assert PgVectorStore._matches_ne_filters({}, {"metadata.state": {"$ne": False}})
    assert PgVectorStore._matches_ne_filters(
        {"state": True}, {"metadata.state": {"$ne": False}}
    )
    assert not PgVectorStore._matches_ne_filters(
        {"state": False}, {"metadata.state": {"$ne": False}}
    )


def test_es_filter_ne_uses_must_not():
    """ES 不等值过滤应使用 must_not，使缺失字段的文档保持命中。"""
    clauses = build_es_filter_clauses({"metadata.state": {"$ne": False}})

    assert clauses == [{"bool": {"must_not": [{"term": {"metadata.state": False}}]}}]


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
                return {"atttypmod": existing_dim} if existing_dim is not None else None
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


def test_keyword_search_accepts_index_names():
    """验证 keyword_search 接受 index_names 参数而非触发接口错误。"""
    import inspect

    from deepclaw.common.vector_store.pgsql import PgVectorStore

    sig = inspect.signature(PgVectorStore.keyword_search)
    assert "index_names" in sig.parameters
    assert "index_name" not in sig.parameters


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

    def fake_fetch_keyword_rows(*, query, index_names, limit, filter_conditions=None):
        recorded["query"] = query
        recorded["index_names"] = index_names
        recorded["limit"] = limit
        recorded["filter_conditions"] = filter_conditions
        return [
            {"id": "1", "content": "alpha", "metadata": {"index_name": "kb_a"}, "score": 0.7},
            {"id": "2", "content": "beta", "metadata": {"index_name": "kb_b"}, "score": 0.6},
        ]

    monkeypatch.setattr(store, "_fetch_keyword_rows", fake_fetch_keyword_rows)

    results = store.keyword_search(
        "hello",
        k=2,
        index_names=["kb_a", "kb_b"],
        filter_conditions={"metadata.state": {"$ne": False}},
    )

    assert recorded == {
        "query": "hello",
        "index_names": ["kb_a", "kb_b"],
        "limit": 2,
        "filter_conditions": {"metadata.state": {"$ne": False}},
    }
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

    assert [(index_name, limit) for index_name, _, limit in requested_indexes] == [
        ("kb_a", 8),
        ("kb_b", 8),
    ]
    assert all(isinstance(query_vector, Vector) for _, query_vector, _ in requested_indexes)
    assert [item["content"] for item in results] == ["alpha", "beta"]

def test_vector_search_existing_embeddings_uses_vector_parameter(monkeypatch):
    """验证已有业务表向量检索使用 pgvector 参数并返回原始字段。

    Args:
        monkeypatch: pytest 提供的依赖替换工具。
    """
    from unittest.mock import MagicMock

    store = PgVectorStore(
        database_url="postgresql://demo",
        embedding_model=FakeEmbeddingModel(),
        embedding_dimensions=3,
    )
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = [{"id": "metric-1", "metric_name": "处理率", "score": 0.9}]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    monkeypatch.setattr(store, "_connect", lambda: connection)

    results = store.vector_search_existing_embeddings(
        "办结率",
        schema_name="ai",
        table_name="metric_config",
        fields=["id", "metric_name"],
        k=3,
    )

    assert results == [{"id": "metric-1", "metric_name": "处理率", "score": 0.9}]
    params = cursor.execute.call_args.args[1]
    assert isinstance(params[0], Vector)
    assert params[0].dimensions() == 3
    assert params[2] == 3
