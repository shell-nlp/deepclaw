from types import SimpleNamespace


def test_resolve_metadata_db_url_prefers_pg_database_url(monkeypatch):
    import deepclaw.web_backend.db as db_module

    monkeypatch.setattr(
        db_module,
        "settings",
        SimpleNamespace(
            PG_DATABASE_URL="postgresql://admin:admin@localhost:55432/deepclaw"
        ),
    )

    resolved = db_module.resolve_metadata_db_url("auth.db")

    assert resolved == "postgresql://admin:admin@localhost:55432/deepclaw"


def test_create_async_engine_checks_postgres_connections_before_reuse(monkeypatch):
    """验证 PostgreSQL 引擎会在复用连接前检查有效性。"""
    import deepclaw.web_backend.db as db_module

    captured = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(db_module, "create_async_engine", fake_create_async_engine)

    db_module.create_async_engine_from_url("postgresql://example/deepclaw")

    assert captured["url"] == "postgresql+asyncpg://example/deepclaw"
    assert captured["kwargs"]["pool_pre_ping"] is True
    assert captured["kwargs"]["pool_recycle"] == 1800


def test_resolve_metadata_db_url_falls_back_to_home_sqlite(monkeypatch, tmp_path):
    import deepclaw.web_backend.db as db_module

    monkeypatch.setattr(db_module, "settings", SimpleNamespace(PG_DATABASE_URL=None))
    monkeypatch.setattr(db_module, "home_path", tmp_path)

    resolved = db_module.resolve_metadata_db_url("channels.db")

    assert resolved == f"sqlite:///{tmp_path / 'channels.db'}"
