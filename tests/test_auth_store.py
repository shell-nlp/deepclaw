import asyncio
import sqlite3
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from sqlmodel import select

from deepclaw.web_backend.auth.models import AccessTokenRecord, utc_now


def build_service(
    *,
    store=None,
    admin_username: str = "admin",
    admin_password: str = "admin-pass-123",
    token_expire_days: int = 30,
):
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore

    store = store or AuthStore("sqlite:///:memory:")
    return AuthService(
        store=store,
        admin_username=admin_username,
        admin_password=admin_password,
        token_expire_days=token_expire_days,
    )


def test_bootstrap_admin_and_issue_token():
    async def _test():
        service = build_service()

        admin = await service.bootstrap_admin_if_needed()
        issued = await service.login(username="admin", password="admin-pass-123")
        actor = await service.authenticate_token(issued.token)

        assert admin is not None
        assert admin.role == "admin"
        assert actor.user.username == "admin"

    asyncio.run(_test())


def build_file_service(
    db_path: Path,
    *,
    admin_username: str = "admin",
    admin_password: str = "admin-pass-123",
    token_expire_days: int = 30,
):
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore

    store = AuthStore(f"sqlite:///{db_path}")
    return AuthService(
        store=store,
        admin_username=admin_username,
        admin_password=admin_password,
        token_expire_days=token_expire_days,
    )


@pytest.fixture
def auth_migration_home(tmp_path, monkeypatch):
    """隔离认证迁移测试的数据库并在结束后删除测试目录。

    Args:
        tmp_path: 当前测试专属的临时目录。
        monkeypatch: 替换运行目录和数据库配置。
    """
    import deepclaw.web_backend.auth.store as auth_store_module
    import deepclaw.web_backend.db as db_module

    with TemporaryDirectory(dir=tmp_path) as directory:
        migration_home = Path(directory) / ".deepclaw"
        monkeypatch.setattr(auth_store_module, "HOME_PATH", migration_home)
        monkeypatch.setattr(db_module, "HOME_PATH", migration_home)
        monkeypatch.setattr(
            db_module, "settings", SimpleNamespace(PG_DATABASE_URL=None, SQLITE_DB_PATH=None)
        )
        yield migration_home


def test_auth_store_migrates_legacy_auth_db_to_deepclaw_home(auth_migration_home):
    import deepclaw.web_backend.auth.store as auth_store_module
    from deepclaw.web_backend.sqlite_migration import migrate_sqlite_metadata

    async def _test():
        async with AsyncExitStack() as databases:
            current_home = auth_migration_home
            legacy_home = current_home.with_name(".langchain_api")
            legacy_home.mkdir()

            legacy_service = build_file_service(
                legacy_home / "auth.db",
                admin_username="admin",
                admin_password="legacy-admin-pass",
            )
            databases.push_async_callback(legacy_service.store.engine.dispose)
            await legacy_service.bootstrap_admin_if_needed()
            await legacy_service.register(username="user", password="user-pass-123")

            migrate_sqlite_metadata(current_home)

            migrated_service = build_service(store=auth_store_module.AuthStore())
            databases.push_async_callback(migrated_service.store.engine.dispose)
            assert migrated_service.store.db_url == f"sqlite:///{(current_home / 'deepclaw.db').as_posix()}"
            issued = await migrated_service.login(username="user", password="user-pass-123")

            assert issued.user.username == "user"
            assert (current_home / ".auth_migrated_from_langchain_api").exists()

    asyncio.run(_test())


def test_auth_store_adds_display_name_to_existing_legacy_schema(tmp_path):
    """验证旧账号表升级后具备可选显示名，且默认不改变用户名。

    Args:
        tmp_path: 用于创建旧版 SQLite 账号库的临时目录。
    """
    from deepclaw.web_backend.auth.store import AuthStore

    db_path = tmp_path / "auth.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE authuser ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "user_id VARCHAR NOT NULL UNIQUE, "
            "username VARCHAR UNIQUE, "
            "email VARCHAR NOT NULL, "
            "password_hash VARCHAR NOT NULL, "
            "role VARCHAR NOT NULL, "
            "is_active BOOLEAN NOT NULL, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL"
            ")"
        )
        connection.execute(
            "INSERT INTO authuser (user_id, username, email, password_hash, role, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("user_legacy", "legacy", "legacy@example.com", "hash", "user", 1, "2026-01-01", "2026-01-01"),
        )

    async def _test():
        store = AuthStore(f"sqlite:///{db_path.as_posix()}")
        try:
            user = await store.get_user_by_username("legacy")
            assert user is not None
            assert user.username == "legacy"
            assert user.display_name is None

            updated = await store.update_user_profile(
                user_id=user.user_id,
                display_name="旧账号显示名",
            )
            assert updated.username == "legacy"
            assert updated.display_name == "旧账号显示名"
        finally:
            await store.engine.dispose()

    asyncio.run(_test())


def test_auth_store_prefers_legacy_auth_data_when_current_db_already_exists(
    auth_migration_home
):
    import deepclaw.web_backend.auth.store as auth_store_module
    from deepclaw.web_backend.sqlite_migration import migrate_sqlite_metadata

    async def _test():
        async with AsyncExitStack() as databases:
            current_home = auth_migration_home
            legacy_home = current_home.with_name(".langchain_api")
            legacy_home.mkdir()
            current_home.mkdir()

            legacy_service = build_file_service(
                legacy_home / "auth.db",
                admin_username="admin",
                admin_password="legacy-admin-pass",
            )
            databases.push_async_callback(legacy_service.store.engine.dispose)
            await legacy_service.bootstrap_admin_if_needed()
            await legacy_service.register(username="legacy-user", password="legacy-user-pass")

            current_service = build_file_service(
                current_home / "auth.db",
                admin_username="admin",
                admin_password="new-admin-pass",
            )
            databases.push_async_callback(current_service.store.engine.dispose)
            await current_service.bootstrap_admin_if_needed()
            await current_service.register(username="current-user", password="current-user-pass")

            migrate_sqlite_metadata(current_home)

            migrated_service = build_service(store=auth_store_module.AuthStore())
            databases.push_async_callback(migrated_service.store.engine.dispose)
            assert migrated_service.store.db_url == f"sqlite:///{(current_home / 'deepclaw.db').as_posix()}"

            admin_issued = await migrated_service.login(
                username="admin",
                password="legacy-admin-pass",
            )
            legacy_user_issued = await migrated_service.login(
                username="legacy-user",
                password="legacy-user-pass",
            )
            current_user_issued = await migrated_service.login(
                username="current-user",
                password="current-user-pass",
            )

            with pytest.raises(ValueError, match="用户名或密码错误。"):
                await migrated_service.login(username="admin", password="new-admin-pass")

            assert admin_issued.user.username == "admin"
            assert legacy_user_issued.user.username == "legacy-user"
            assert current_user_issued.user.username == "current-user"

    asyncio.run(_test())


def test_auth_store_defaults_to_pg_database_url_when_configured(monkeypatch):
    import deepclaw.web_backend.db as db_module
    import deepclaw.web_backend.auth.store as auth_store_module

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        db_module,
        "settings",
        SimpleNamespace(
            PG_DATABASE_URL="postgresql://admin:admin@localhost:55432/deepclaw"
        ),
    )
    monkeypatch.setattr(
        auth_store_module,
        "migrate_legacy_auth_db_if_needed",
        lambda target_home: None,
    )
    monkeypatch.setattr(
        auth_store_module,
        "create_async_engine_from_url",
        lambda db_url: captured.setdefault("db_url", db_url) or object(),
    )
    monkeypatch.setattr(
        auth_store_module,
        "build_async_sessionmaker",
        lambda engine: captured.setdefault("engine", engine) or object(),
    )

    auth_store_module.AuthStore()

    assert captured["db_url"] == "postgresql://admin:admin@localhost:55432/deepclaw"


def test_register_rejects_duplicate_username():
    async def _test():
        service = build_service()

        await service.register(username="user", password="secret-123")

        with pytest.raises(ValueError, match="该用户名已被注册"):
            await service.register(username="user", password="secret-456")

    asyncio.run(_test())


@pytest.mark.filterwarnings("error:DELETE statement on table 'accesstokenrecord':sqlalchemy.exc.SAWarning")
def test_authenticate_expired_token_deletes_token_record(tmp_path):
    """验证并发认证过期令牌时，每个请求都被拒绝且只需删除一次。

    Args:
        tmp_path: 用于创建独立 SQLite 数据库的测试目录。
    """
    async def _test():
        """并发提交同一个过期凭据并检查数据库。"""
        service = build_file_service(tmp_path / "auth.db")
        user = await service.register(username="user", password="secret-123")
        issued = await service.store.issue_access_token(
            user=user,
            raw_token="expired-token",
            expire_days=1,
        )

        async with service.store.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == issued.record.token_hash
                )
            )
            record = result.one()
            record.expires_at = utc_now() - timedelta(seconds=1)
            session.add(record)
            await session.commit()

        results = await asyncio.gather(
            *(service.authenticate_token(issued.token) for _ in range(4)),
            return_exceptions=True,
        )
        for result in results:
            assert isinstance(result, ValueError)
            assert str(result) == "登录状态已失效，请重新登录。"

        async with service.store.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == issued.record.token_hash
                )
            )
            deleted_record = result.first()

        assert deleted_record is None

    asyncio.run(_test())


def test_reconcile_access_tokens_clamps_legacy_expiry_to_one_day():
    async def _test():
        service = build_service(token_expire_days=1)
        user = await service.register(username="legacy", password="secret-123")
        issued = await service.store.issue_access_token(
            user=user,
            raw_token="legacy-token",
            expire_days=30,
        )

        async with service.store.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == issued.record.token_hash
                )
            )
            record = result.one()
            record.created_at = utc_now() - timedelta(hours=12)
            record.expires_at = record.created_at + timedelta(days=30)
            session.add(record)
            await session.commit()

        await service.store.reconcile_access_token_expiry(expire_days=1)

        async with service.store.async_session() as session:
            result = await session.exec(
                select(AccessTokenRecord).where(
                    AccessTokenRecord.token_hash == issued.record.token_hash
                )
            )
            updated_record = result.one()

        assert updated_record.expires_at == updated_record.created_at + timedelta(days=1)

    asyncio.run(_test())


def test_authenticate_throttles_last_used_at_writes():
    """验证令牌校验只在节流窗口外才刷新 last_used_at。"""

    async def _test():
        from deepclaw.web_backend.auth.store import (
            ACCESS_TOKEN_LAST_USED_THROTTLE,
        )

        service = build_service()
        user = await service.register(username="user", password="secret-123")
        issued = await service.store.issue_access_token(
            user=user,
            raw_token="throttled-token",
            expire_days=1,
        )

        async def backdate(seconds: int) -> None:
            """把令牌的 last_used_at 回拨到指定秒数之前。

            Args:
                seconds: 回拨的秒数。
            """
            async with service.store.async_session() as session:
                result = await session.exec(
                    select(AccessTokenRecord).where(
                        AccessTokenRecord.token_hash == issued.record.token_hash
                    )
                )
                record = result.one()
                record.last_used_at = utc_now() - timedelta(seconds=seconds)
                session.add(record)
                await session.commit()

        async def read_last_used_at():
            """读取令牌当前的 last_used_at。

            Args: 无。
            """
            async with service.store.async_session() as session:
                result = await session.exec(
                    select(AccessTokenRecord).where(
                        AccessTokenRecord.token_hash == issued.record.token_hash
                    )
                )
                return result.one().last_used_at

        # 窗口内：回拨 10 秒后校验，不应写库。
        await backdate(10)
        within_window = await read_last_used_at()
        await service.authenticate_token(issued.token)
        assert await read_last_used_at() == within_window

        # 窗口外：回拨 120 秒后校验，应当刷新。
        await backdate(120)
        outside_window = await read_last_used_at()
        await service.authenticate_token(issued.token)
        refreshed = await read_last_used_at()

        assert refreshed > outside_window
        assert refreshed > utc_now() - timedelta(seconds=5)
        assert ACCESS_TOKEN_LAST_USED_THROTTLE == timedelta(seconds=60)

    asyncio.run(_test())


def test_login_uses_username_not_email():
    """验证登录只认用户名，邮箱不再是登录标识。

    Args:
        无。
    """

    async def _test():
        service = build_service()
        await service.register(username="alice", password="alice-pass-1", email="alice@example.com")

        issued = await service.login(username="alice", password="alice-pass-1")
        assert issued.user.username == "alice"
        assert issued.user.email == "alice@example.com"

        with pytest.raises(ValueError, match="用户名或密码错误。"):
            await service.login(username="alice@example.com", password="alice-pass-1")

    asyncio.run(_test())


def test_usernames_are_case_insensitive():
    """验证用户名归一化为小写，大小写不同视为同一账号。

    Args:
        无。
    """

    async def _test():
        service = build_service()
        await service.register(username="MixedCase", password="mixed-pass-1")

        issued = await service.login(username="mixedcase", password="mixed-pass-1")
        assert issued.user.username == "mixedcase"

        with pytest.raises(ValueError, match="该用户名已被注册"):
            await service.register(username="MIXEDCASE", password="other-pass-1")

    asyncio.run(_test())
