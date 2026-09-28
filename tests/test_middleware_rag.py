from deepclaw.common.vector_store.base import AbstractVectorStore
from deepclaw.middleware.rag import RAGMiddleware


class DummyVectorStore:
    """记录 RRF 混合检索调用的向量库替身。"""

    def __init__(self):
        self.rrf_calls = []

    def retrieve_with_rrf(self, query, k=3, index_names=None, filter_conditions=None):
        """记录调用并返回固定的混合检索结果。

        Args:
            query: 查询文本。
            k: 召回数量。
            index_names: 目标索引列表。
            filter_conditions: 元数据过滤条件。
        """
        self.rrf_calls.append({
            "query": query,
            "k": k,
            "index_names": index_names,
            "filter_conditions": filter_conditions,
        })
        return [
            {
                "content": "rrf result",
                "metadata": {"source": "hybrid"},
                "score": 0.5,
            }
        ]


def test_rag_retrieval_uses_hybrid_rrf():
    """RAG 检索统一走 BM25 + 向量的 RRF 混合检索。"""
    store = DummyVectorStore()
    middleware = RAGMiddleware(store)

    results = middleware._get_retrieve_result(
        query="hello",
        index_name="kb_demo_passages",
        k=2,
    )

    assert store.rrf_calls == [
        {
            "query": "hello",
            "k": 2,
            "index_names": ["kb_demo_passages"],
            "filter_conditions": {"metadata.state": {"$ne": False}},
        }
    ]
    assert results[0][0].page_content == "rrf result"
    assert results[0][0].metadata == {"source": "hybrid"}
    assert results[0][1] == 0.5


def test_merge_results_rrf_ranks_shared_documents_first():
    """RRF 让两个召回列表共同命中的文档排到最前。"""
    vector_results = [
        {"id": "a", "content": "A"},
        {"id": "b", "content": "B"},
    ]
    keyword_results = [
        {"id": "c", "content": "C"},
        {"id": "b", "content": "B"},
    ]

    merged = AbstractVectorStore.merge_results_rrf(
        vector_results=vector_results,
        keyword_results=keyword_results,
        k=3,
    )

    assert [item["id"] for item in merged] == ["b", "a", "c"]
