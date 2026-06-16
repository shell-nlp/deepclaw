import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlmodel import select

from deepclaw.web_backend.auth.models import AccessTokenRecord, utc_now


def build_service(
    *,
    store=None,
    admin_email: str = "admin@example.com",
    admin_password: str = "admin-pass-123",
    token_expire_days: int = 30,
):
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore

    store = store or AuthStore("sqlite:///:memory:")
    return AuthService(
        store=store,
        admin_email=admin_email,
        admin_password=admin_password,
        token_expire_days=token_expire_days,
    )


def test_bootstrap_admin_and_issue_token():
    async def _test():
        service = build_service()

        admin = await service.bootstrap_admin_if_needed()
        issued = await service.login(email="admin@example.com", password="admin-pass-123")
        actor = await service.authenticate_token(issued.token)

        assert admin is not None
        assert admin.role == "admin"
        assert actor.user.email == "admin@example.com"

    asyncio.run(_test())


def build_file_service(
    db_path: Path,
    *,
    admin_email: str = "admin@example.com",
    admin_password: str = "admin-pass-123",
    token_expire_days: int = 30,
):
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore

    store = AuthStore(f"sqlite:///{db_path}")
    return AuthService(
        store=store,
        admin_email=admin_email,
        admin_password=admin_password,
        token_expire_days=token_expire_days,
    )


def test_auth_store_migrates_legacy_auth_db_to_deepclaw_home(tmp_path, monkeypatch):
    import deepclaw.web_backend.auth.store as auth_store_module

    async def _test():
        legacy_home = tmp_path / ".langchain_api"
        current_home = tmp_path / ".deepclaw"
        legacy_home.mkdir()

        legacy_service = build_file_service(
            legacy_home / "auth.db",
            admin_email="admin@qq.com",
            admin_password="legacy-admin-pass",
        )
        await legacy_service.bootstrap_admin_if_needed()
        await legacy_service.register(email="user@example.com", password="user-pass-123")

        monkeypatch.setattr(auth_store_module, "home_path", current_home)

        migrated_service = build_service(store=auth_store_module.AuthStore())
        issued = await migrated_service.login(email="user@example.com", password="user-pass-123")

        assert issued.user.email == "user@example.com"
        assert (current_home / ".auth_migrated_from_langchain_api").exists()

    asyncio.run(_test())


def test_auth_store_prefers_legacy_auth_data_when_current_db_already_exists(
    tmp_path, monkeypatch
):
    import deepclaw.web_backend.auth.store as auth_store_module

    async def _test():
        legacy_home = tmp_path / ".langchain_api"
        current_home = tmp_path / ".deepclaw"
        legacy_home.mkdir()
        current_home.mkdir()

        legacy_service = build_file_service(
            legacy_home / "auth.db",
            admin_email="admin@qq.com",
            admin_password="legacy-admin-pass",
        )
        await legacy_service.bootstrap_admin_if_needed()
        await legacy_service.register(email="legacy-user@example.com", password="legacy-user-pass")

        current_service = build_file_service(
            current_home / "auth.db",
            admin_email="admin@qq.com",
            admin_password="new-admin-pass",
        )
        await current_service.bootstrap_admin_if_needed()
        await current_service.register(email="current-user@example.com", password="current-user-pass")

        monkeypatch.setattr(auth_store_module, "home_path", current_home)

        migrated_service = build_service(store=auth_store_module.AuthStore())

        admin_issued = await migrated_service.login(
            email="admin@qq.com",
            password="legacy-admin-pass",
        )
        legacy_user_issued = await migrated_service.login(
            email="legacy-user@example.com",
            password="legacy-user-pass",
        )
        current_user_issued = await migrated_service.login(
            email="current-user@example.com",
            password="current-user-pass",
        )

        with pytest.raises(ValueError, match="邮箱或密码错误。"):
            await migrated_service.login(email="admin@qq.com", password="new-admin-pass")

        assert admin_issued.user.email == "admin@qq.com"
        assert legacy_user_issued.user.email == "legacy-user@example.com"
        assert current_user_issued.user.email == "current-user@example.com"

    asyncio.run(_test())


def test_register_rejects_duplicate_email():
    async def _test():
        service = build_service()

        await service.register(email="user@example.com", password="secret-123")

        with pytest.raises(ValueError, match="该邮箱已注册，请直接登录。"):
            await service.register(email="user@example.com", password="secret-456")

    asyncio.run(_test())


def test_authenticate_expired_token_deletes_token_record():
    async def _test():
        service = build_service()
        user = await service.register(email="user@example.com", password="secret-123")
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

        with pytest.raises(ValueError, match="登录状态已失效，请重新登录。"):
            await service.authenticate_token(issued.token)

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
        user = await service.register(email="legacy@example.com", password="secret-123")
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
