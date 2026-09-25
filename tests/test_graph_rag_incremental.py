"""图谱跨批次写入与 PostgreSQL 检索回归测试。"""

from copy import deepcopy
from unittest.mock import MagicMock

from langchain_core.documents import Document

from deepclaw.common.graph_rag.pg import PgGraphRAG
from deepclaw.common.graph_rag.elastic import ElasticGraphRAG
from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore
from deepclaw.common.vector_store.pgsql import PgVectorStore


class MemoryPgVectorStore(PgVectorStore):
    """用内存保存索引的 PG 替身。"""

    def __init__(self):
        """初始化内存索引。"""
        super().__init__(database_url="postgresql://fake")
        self.records = {}
        self.deleted_batches = []

    def batch_get(self, doc_ids, index_name=None):
        """按 ID 返回索引记录。

        Args:
            doc_ids: 文档 ID。
            index_name: 索引名称。
        """
        return [deepcopy(self.records.get((index_name, doc_id))) for doc_id in doc_ids]

    def add_batch(self, documents, index_name=None):
        """保存一批文档。

        Args:
            documents: 文档列表。
            index_name: 索引名称。
        """
        for doc in documents:
            self.records[(index_name, doc["id"])] = deepcopy(doc)
        return [doc["id"] for doc in documents]

    def search(self, query=None, k=3, filter_conditions=None, index_names=None):
        """过滤内存记录。

        Args:
            query: 查询文本。
            k: 最多返回数量。
            filter_conditions: 元数据条件。
            index_names: 索引列表。
        """
        results = []
        for (index, _), doc in self.records.items():
            if index not in (index_names or []):
                continue
            if filter_conditions and not all(
                bool(
                    set(value if isinstance(value, list) else [value])
                    & set(doc["metadata"].get(field.removeprefix("metadata."), []))
                )
                for field, value in filter_conditions.items()
            ):
                continue
            results.append(deepcopy(doc))
        return results[:k]

    def update(self, doc_id, content=None, metadata=None, index_name=None):
        """更新文档元数据。

        Args:
            doc_id: 文档 ID。
            content: 可选正文。
            metadata: 新元数据。
            index_name: 索引名称。
        """
        self.records[(index_name, doc_id)]["metadata"] = deepcopy(metadata)
        return True

    def delete(self, doc_id, index_name=None):
        """删除索引记录。

        Args:
            doc_id: 文档 ID。
            index_name: 索引名称。
        """
        return self.records.pop((index_name, doc_id), None) is not None

    def delete_batch(self, doc_ids, index_name=None):
        """记录批量删除并执行。

        Args:
            doc_ids: 文档 ID。
            index_name: 索引名称。
        """
        self.deleted_batches.append((index_name, list(doc_ids)))
        return [self.delete(doc_id, index_name=index_name) for doc_id in doc_ids]

    def list_ids_by_filter(self, index_name, filter_conditions):
        """按元数据字段查找全部篇章 ID。

        Args:
            index_name: 索引名称。
            filter_conditions: 元数据精确条件。
        """
        return [
            doc_id
            for (index, doc_id), doc in self.records.items()
            if index == index_name and all(
                doc["metadata"].get(field.removeprefix("metadata.")) == value
                for field, value in filter_conditions.items()
            )
        ]


def test_shared_entities_survive_incremental_upload_and_replacement():
    """跨批次实体和关系保持全部来源；重传时移除过期关联。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    rag.add_documents(
        [Document(page_content="first", id="p1", metadata={"triplets": [["A", "knows", "B"]]})]
    )
    rag.add_documents(
        [Document(page_content="second", id="p2", metadata={"triplets": [["A", "knows", "B"]]})]
    )
    entity = next(
        doc for (index, _), doc in store.records.items()
        if index == "kb_entities" and doc["content"] == "a"
    )
    relation = next(doc for (index, _), doc in store.records.items() if index == "kb_relations")
    assert entity["metadata"]["passage_ids"] == ["p1", "p2"]
    assert relation["metadata"]["passage_ids"] == ["p1", "p2"]

    rag.add_documents([Document(page_content="replaced", id="p1", metadata={"triplets": []})],
                      extract_triplets=False)
    assert relation["id"] in [key[1] for key in store.records if key[0] == "kb_relations"]
    rag.delete_documents(["p2"])
    assert not any(index == "kb_relations" for index, _ in store.records)
    assert not any(index == "kb_entities" for index, _ in store.records)


def test_batch_replacement_keeps_shared_passage_links():
    """同批重传时保留仍由其他篇章引用的实体和关系。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    triplets = [["A", "knows", "B"]]
    rag.add_documents([
        Document(page_content="first", id="p1", metadata={"triplets": triplets}),
        Document(page_content="second", id="p2", metadata={"triplets": triplets}),
    ])
    rag.add_documents([
        Document(page_content="removed", id="p1", metadata={"triplets": []}),
        Document(page_content="kept", id="p2", metadata={"triplets": triplets}),
    ], extract_triplets=False)
    for kind in ("entities", "relations"):
        docs = [doc for (index, _), doc in store.records.items() if index == f"kb_{kind}"]
        assert docs
        assert all(doc["metadata"]["passage_ids"] == ["p2"] for doc in docs)


def test_upsert_by_source_removes_obsolete_chunks_and_preserves_other_sources():
    """来源替换删掉过期 chunk，但不破坏其他来源共享的图谱。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    triplets = [["A", "knows", "B"]]
    rag.upsert_documents_by_source(
        [
            Document(page_content="old 1", id="old1", metadata={"triplets": triplets}),
            Document(page_content="old 2", id="old2", metadata={"triplets": triplets}),
        ],
        source="file-1", extract_triplets=False,
    )
    rag.upsert_documents_by_source(
        [Document(page_content="other", id="other", metadata={"triplets": triplets})],
        source="file-2", extract_triplets=False,
    )
    rag.upsert_documents_by_source(
        [Document(page_content="new", id="new", metadata={"triplets": triplets})],
        source="file-1", extract_triplets=False,
    )
    assert store.list_ids_by_filter(
        "kb_passages", {"metadata.document_id": "file-1"}
    ) == ["new"]
    assert ("kb_passages", "other") in store.records
    relations = [
        doc for (index, _), doc in store.records.items()
        if index == "kb_relations"
    ]
    assert len(relations) == 1
    assert relations[0]["metadata"]["passage_ids"] == ["new", "other"]

    rag.delete_documents_by_source("file-1")
    assert relations[0]["id"] in [
        doc_id for index, doc_id in store.records if index == "kb_relations"
    ]
    assert store.records[("kb_relations", relations[0]["id"])]["metadata"]["passage_ids"] == [
        "other"
    ]


def test_pg_delete_graph_removes_more_than_default_search_page():
    """按批次循环删除整个 PG 图。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    for number in range(8):
        store.records[("kb_passages", str(number))] = {
            "id": str(number), "content": "", "metadata": {}
        }
    rag.delete_graph()
    assert not store.records
    assert len(store.deleted_batches[0][1]) == 8


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
        index_names=["kb_relations"],
        filter_conditions={"metadata.passage_ids": ["p1", "p2"]},
    )

    assert "(metadata -> 'passage_ids') ?| %(value_0)s" in captured["statement"]
    assert captured["params"]["value_0"] == ["p1", "p2"]


def test_es_batch_insert_preserves_explicit_graph_ids():
    """ES 批量写入必须保留图谱指定的实体 ID。"""
    client = MagicMock()
    client.bulk.return_value = {"items": [{"index": {"_id": "ent_1"}}]}
    embeddings = MagicMock()
    embeddings.embed_query.return_value = [0.1, 0.2]
    store = ElasticsearchVectorStore(
        url="http://localhost:9200", embedding_model=embeddings
    )
    store._es_client = client

    assert store.add_batch(
        [{"id": "ent_1", "content": "Alice", "metadata": {"id": "ent_1"}}],
        index_name="kb_entities",
    ) == ["ent_1"]
    assert client.bulk.call_args.kwargs["operations"][0]["index"]["_id"] == "ent_1"


def test_pg_relation_eviction_stays_within_expanded_candidates(monkeypatch):
    """PG 候选裁剪不引入图外关系。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    monkeypatch.setattr(rag, "_extract_query_entities", lambda query: [])
    calls = []

    def vector_search(query, k=3, index_names=None, filter_conditions=None, min_similarity=None):
        """模拟种子、扩展和篇章召回。

        Args:
            query: 检索问题。
            k: 返回上限。
            index_names: 索引名称。
            filter_conditions: 图谱邻接过滤。
            min_similarity: 最低相似度。
        """
        if index_names == ["kb_relations"] and not filter_conditions:
            return [{"id": "r1"}, {"id": "r2"}]
        return []

    def vector_search_by_ids(query, doc_ids, index_name, k):
        """记录候选 ID 并返回裁剪结果。

        Args:
            query: 检索问题。
            doc_ids: 候选关系 ID。
            index_name: 索引名称。
            k: 返回上限。
        """
        calls.append((set(doc_ids), index_name, k))
        return [{"id": "r2"}]

    monkeypatch.setattr(store, "vector_search", vector_search)
    monkeypatch.setattr(store, "vector_search_by_ids", vector_search_by_ids)
    result = rag.retrieve("query", expansion_degree=0, relation_limit=1, return_debug=True)

    assert calls == [({"r1", "r2"}, "kb_relations", 1)]
    assert result["kept_relation_ids"] == ["r2"]


def test_shared_retrieval_filters_cross_source_graph(monkeypatch):
    """共享实体跨来源连接时仅返回目标来源篇章。"""
    store = MemoryPgVectorStore()
    rag = PgGraphRAG(store, "kb")
    triplets = [["A", "knows", "B"]]
    rag.upsert_documents_by_source(
        [Document(page_content="first", id="p1", metadata={"triplets": triplets})],
        source="first", extract_triplets=False,
    )
    rag.upsert_documents_by_source(
        [Document(page_content="second", id="p2", metadata={"triplets": triplets})],
        source="second", extract_triplets=False,
    )
    monkeypatch.setattr(rag, "_extract_query_entities", lambda query: ["A"])

    def vector_search(query, k=3, index_names=None, min_similarity=None,
                      filter_conditions=None):
        """模拟向量召回并严格检查来源过滤。

        Args:
            query: 查询文本。
            k: 结果数量。
            index_names: 索引名称。
            min_similarity: 最低分数。
            filter_conditions: 元数据条件。
        """
        if index_names == ["kb_entities"]:
            return [{"id": next(
                doc_id for (index, doc_id), doc in store.records.items()
                if index == "kb_entities" and doc["content"] == "a"
            )}]
        if index_names == ["kb_passages"]:
            return [
                {"id": doc_id, "content": doc["content"], "score": 0.9}
                for (index, doc_id), doc in store.records.items()
                if index == "kb_passages"
                and (not filter_conditions or doc_id in store.list_ids_by_filter(
                    "kb_passages", filter_conditions
                ))
            ][:k]
        return []

    def vector_search_by_ids(query, doc_ids, index_name, k):
        """返回指定 ID 的匹配篇章。

        Args:
            query: 查询文本。
            doc_ids: 候选 ID。
            index_name: 索引名称。
            k: 结果数量。
        """
        return [
            {"id": doc_id, "content": store.records[(index_name, doc_id)]["content"],
             "score": 0.9}
            for doc_id in doc_ids[:k]
        ]

    monkeypatch.setattr(store, "vector_search", vector_search)
    monkeypatch.setattr(store, "vector_search_by_ids", vector_search_by_ids)
    passages = rag.retrieve(
        "query", filter_conditions={"metadata.document_id": "first"}
    )
    assert [passage["id"] for passage in passages] == ["p1"]
    assert rag.retrieve(
        "query", min_similarity=0.95,
        filter_conditions={"metadata.document_id": "first"},
    ) == []


def test_es_and_pg_use_the_same_retrieval_implementation():
    """两个后端共用基类检索算法。"""
    from deepclaw.common.graph_rag.base import BaseGraphRAG

    assert PgGraphRAG.retrieve is BaseGraphRAG.retrieve
    assert ElasticGraphRAG.retrieve is BaseGraphRAG.retrieve


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
