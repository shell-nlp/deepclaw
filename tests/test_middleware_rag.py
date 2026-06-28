from deepclaw.middleware.rag import RAGMiddleware


class DummyVectorStore:
    def __init__(self):
        self.calls = []

    def retrieve(self, query, k=3, index_names=None):
        self.calls.append({"query": query, "k": k, "index_names": index_names})
        return [
            {
                "content": "fallback result",
                "metadata": {"source": "vector-store"},
                "score": 0.81,
            }
        ]


def test_graph_retrieve_falls_back_to_normal_retrieve_for_non_es_store():
    store = DummyVectorStore()
    middleware = RAGMiddleware(store)

    results = middleware._get_retrieve_result(
        query="hello",
        index_name="kb_demo_passages",
        graph_name="kb_demo",
        k=2,
    )

    assert store.calls == [{"query": "hello", "k": 2, "index_names": ["kb_demo_passages"]}]
    assert len(results) == 1
    assert results[0][0].page_content == "fallback result"
    assert results[0][0].metadata == {"source": "vector-store"}
    assert results[0][1] == 0.81
