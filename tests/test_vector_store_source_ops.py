"""向量库来源级读写与过滤回归测试。

覆盖 list_ids_by_filter 的分页与参数绑定行为，以及 add_batch 保留显式 ID 的行为。
"""

from unittest.mock import MagicMock

from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore


def test_pg_metadata_array_filter_matches_any_value(monkeypatch):
    """PG 数组过滤使用任一匹配和原生列表参数。"""
    store = PgVectorStore(database_url="postgresql://fake")
    captured = {}

    class Cursor:
        """记录查询的游标替身。"""

        def execute(self, statement, params=None):
            """保存 SQL 及参数。

            Args:
                statement: SQL 文本。
                params: 绑定参数。
            """
            captured["statement"] = statement
            captured["params"] = params

        def fetchall(self):
            """返回空查询结果。"""
            return []

        def __enter__(self):
            """返回游标自身。"""
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """结束游标上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常实例。
                traceback: 异常调用栈。
            """

    class Connection:
        """提供游标的连接替身。"""

        def cursor(self):
            """创建查询游标。"""
            return Cursor()

        def __enter__(self):
            """返回连接自身。"""
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """结束连接上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常实例。
                traceback: 异常调用栈。
            """

    monkeypatch.setattr(store, "_ensure_base_schema", lambda: None)
    monkeypatch.setattr(store, "_connect", lambda: Connection())
    store.search(
        index_names=["kb_passages"],
        filter_conditions={"metadata.passage_ids": ["p1", "p2"]},
    )

    assert "(metadata -> 'passage_ids') ?| %(value_0)s" in captured["statement"]
    assert captured["params"]["value_0"] == ["p1", "p2"]

def test_es_batch_insert_preserves_explicit_ids():
    """ES 批量写入必须保留传入的显式 ID。"""
    client = MagicMock()
    client.bulk.return_value = {"items": [{"index": {"_id": "p1"}}]}
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1, 0.2]
    store = ElasticsearchVectorStore(
        url="http://localhost:9200", embedding_model=embeddings
    )
    store._es_client = client

    assert store.add_batch(
        [{"id": "p1", "content": "Alice", "metadata": {"id": "p1"}}],
        index_name="kb_passages",
    ) == ["p1"]
    assert client.bulk.call_args.kwargs["operations"][0]["index"]["_id"] == "p1"

def test_es_list_ids_by_filter_scrolls_all_pages():
    """ES 来源查询会遍历所有 scroll 页。"""
    client = MagicMock()
    client.indices.exists.return_value = True
    client.search.return_value = {
        "_scroll_id": "cursor-1",
        "hits": {"hits": [{"_id": "p1"}, {"_id": "p2"}]},
    }
    client.scroll.side_effect = [
        {"_scroll_id": "cursor-2", "hits": {"hits": [{"_id": "p3"}]}},
        {"_scroll_id": "cursor-3", "hits": {"hits": []}},
    ]
    store = ElasticsearchVectorStore(url="http://localhost:9200")
    store._es_client = client
    assert store.list_ids_by_filter(
        "kb_passages", {"metadata.document_id": "file-1"}
    ) == ["p1", "p2", "p3"]
    client.clear_scroll.assert_called_once_with(scroll_id="cursor-3")

def test_pg_list_ids_by_filter_uses_bound_source(monkeypatch):
    """PG 来源查询通过 SQL 参数绑定，不受默认搜索页限制。"""
    store = PgVectorStore(database_url="postgresql://fake")
    captured = {}

    class Cursor:
        """用于捕获查询参数的游标。"""

        def execute(self, statement, params=None):
            """记录 SQL 与参数。

            Args:
                statement: SQL 语句。
                params: 查询参数。
            """
            captured["statement"] = statement
            captured["params"] = params

        def fetchall(self):
            """返回模拟 ID。"""
            return [{"id": "p1"}, {"id": "p2"}]

        def __enter__(self):
            """进入游标上下文。"""
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """退出游标上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常值。
                traceback: 异常堆栈。
            """

    class Connection:
        """用于创建游标的连接。"""

        def cursor(self):
            """返回游标。"""
            return Cursor()

        def __enter__(self):
            """进入连接上下文。"""
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """退出连接上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常值。
                traceback: 异常堆栈。
            """

    monkeypatch.setattr(store, "_ensure_base_schema", lambda: None)
    monkeypatch.setattr(store, "_connect", lambda: Connection())
    assert store.list_ids_by_filter(
        "kb_passages", {"metadata.document_id": "file-1"}
    ) == ["p1", "p2"]
    assert "metadata ->> 'document_id' = %(value_0)s" in captured["statement"]
    assert captured["params"]["value_0"] == "file-1"
