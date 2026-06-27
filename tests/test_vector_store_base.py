import pytest

from deepclaw.common.vector_store.base import AbstractVectorStore


class DummyStore(AbstractVectorStore):
    def add(self, content, metadata=None, doc_id=None, index_name=None):
        raise NotImplementedError

    def add_batch(self, documents, index_name=None):
        raise NotImplementedError

    def update(self, doc_id, content=None, metadata=None, index_name=None):
        raise NotImplementedError

    def delete(self, doc_id, index_name=None):
        raise NotImplementedError

    def delete_batch(self, doc_ids, index_name=None):
        raise NotImplementedError

    def get(self, doc_id, index_name=None):
        raise NotImplementedError

    def exists(self, doc_id, index_name=None):
        raise NotImplementedError

    def count(self, filter_conditions=None, index_name=None, index_names=None):
        raise NotImplementedError

    def search(self, query=None, k=3, filter_conditions=None, index_name=None, index_names=None):
        raise NotImplementedError

    def vector_search(self, query, k=3, index_name=None, index_names=None, min_similarity=None):
        raise NotImplementedError

    def keyword_search(self, query, k=3, index_name=None, index_names=None):
        raise NotImplementedError


def test_resolve_index_names_accepts_single_name():
    store = DummyStore()
    assert store.resolve_index_names(index_name="kb_demo") == ["kb_demo"]


def test_resolve_index_names_accepts_multiple_names_and_deduplicates():
    store = DummyStore()
    assert store.resolve_index_names(index_names=["kb_a", "kb_b", "kb_a"]) == ["kb_a", "kb_b"]


def test_resolve_index_names_rejects_conflicting_arguments():
    store = DummyStore()
    with pytest.raises(ValueError, match="index_name and index_names"):
        store.resolve_index_names(index_name="kb_a", index_names=["kb_b"])


def test_merge_results_prefers_vector_hits_and_deduplicates_by_content():
    store = DummyStore()
    merged = store.merge_results(
        vector_results=[
            {"content": "alpha", "metadata": {"source": "vector"}, "score": 0.92},
            {"content": "beta", "metadata": {"source": "vector"}, "score": 0.88},
        ],
        keyword_results=[
            {"content": "beta", "metadata": {"source": "keyword"}, "score": 0.77},
            {"content": "gamma", "metadata": {"source": "keyword"}, "score": 0.73},
        ],
        k=3,
    )

    assert [item["content"] for item in merged] == ["alpha", "beta", "gamma"]
    assert merged[1]["metadata"]["source"] == "vector"
