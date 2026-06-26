from types import SimpleNamespace

from deepclaw.common.vector_store import factory


def test_create_default_vector_store_uses_configured_elasticsearch_backend(monkeypatch):
    class FakeStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(
        factory,
        "settings",
        SimpleNamespace(
            VECTOR_STORE_BACKEND="elasticsearch",
            ES_URL="http://localhost:9200",
            ES_URSR="demo",
            ES_PWD="secret",
            PG_DATABASE_URL=None,
        ),
    )
    monkeypatch.setattr(factory, "ElasticsearchVectorStore", FakeStore)

    store = factory.create_default_vector_store(embedding_model="emb")

    assert isinstance(store, FakeStore)
    assert store.kwargs == {
        "url": "http://localhost:9200",
        "username": "demo",
        "password": "secret",
        "embedding_model": "emb",
    }


def test_create_default_vector_store_uses_configured_pgsql_backend(monkeypatch):
    captured = {}

    class FakePgStore:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        factory,
        "settings",
        SimpleNamespace(
            VECTOR_STORE_BACKEND="pgsql",
            ES_URL=None,
            ES_URSR=None,
            ES_PWD=None,
            PG_DATABASE_URL="postgresql://admin:admin@localhost:55432/deepclaw",
        ),
    )

    def fake_import():
        return FakePgStore

    monkeypatch.setattr(factory, "_load_pg_vector_store", fake_import, raising=False)

    store = factory.create_default_vector_store(
        embedding_model="emb", embedding_dimensions=1536
    )

    assert isinstance(store, FakePgStore)
    assert captured == {
        "database_url": "postgresql://admin:admin@localhost:55432/deepclaw",
        "embedding_model": "emb",
        "embedding_dimensions": 1536,
    }
