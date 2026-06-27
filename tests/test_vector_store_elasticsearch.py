from deepclaw.common.vector_store.elasticsearch import ElasticsearchVectorStore


class FakeEmbeddingModel:
    def embed_query(self, query: str):
        return [0.1, 0.2, 0.3]


class FakeESClient:
    def __init__(self):
        self.search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "1",
                        "_score": 0.91,
                        "_source": {"content": "alpha", "metadata": {"id": "1"}},
                    },
                    {
                        "_id": "2",
                        "_score": 0.82,
                        "_source": {"content": "beta", "metadata": {"id": "2"}},
                    },
                ]
            }
        }


def test_vector_search_forwards_multiple_index_names():
    store = ElasticsearchVectorStore(
        url="http://localhost:9200",
        embedding_model=FakeEmbeddingModel(),
    )
    store._es_client = FakeESClient()

    store.vector_search(query="hello", k=2, index_names=["kb_a", "kb_b"])

    assert store.es_client.search_calls[0]["index"] == ["kb_a", "kb_b"]


def test_retrieve_merges_vector_and_keyword_hits_without_duplicates(monkeypatch):
    store = ElasticsearchVectorStore(
        url="http://localhost:9200",
        embedding_model=FakeEmbeddingModel(),
    )

    monkeypatch.setattr(
        store,
        "vector_search",
        lambda *args, **kwargs: [
            {"content": "alpha", "metadata": {"source": "vector"}, "score": 0.9},
            {"content": "beta", "metadata": {"source": "vector"}, "score": 0.8},
        ],
    )
    monkeypatch.setattr(
        store,
        "keyword_search",
        lambda *args, **kwargs: [
            {"content": "beta", "metadata": {"source": "keyword"}, "score": 0.7},
            {"content": "gamma", "metadata": {"source": "keyword"}, "score": 0.6},
        ],
    )

    results = store.retrieve(query="hello", k=3, index_names=["kb_a", "kb_b"])
    assert [item["content"] for item in results] == ["alpha", "beta", "gamma"]
