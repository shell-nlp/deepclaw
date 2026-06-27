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


def test_resolve_metadata_db_url_falls_back_to_home_sqlite(monkeypatch, tmp_path):
    import deepclaw.web_backend.db as db_module

    monkeypatch.setattr(db_module, "settings", SimpleNamespace(PG_DATABASE_URL=None))
    monkeypatch.setattr(db_module, "home_path", tmp_path)

    resolved = db_module.resolve_metadata_db_url("channels.db")

    assert resolved == f"sqlite:///{tmp_path / 'channels.db'}"
