from datetime import timedelta

import pytest
from sqlmodel import Session, select


def build_service(*, token_expire_days: int = 30):
    from langchain_api.web_backend.auth.service import AuthService
    from langchain_api.web_backend.auth.store import AuthStore

    store = AuthStore("sqlite:///:memory:")
    return AuthService(
        store=store,
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        token_expire_days=token_expire_days,
    )


def test_bootstrap_admin_and_issue_token():
    service = build_service()

    admin = service.bootstrap_admin_if_needed()
    issued = service.login(email="admin@example.com", password="admin-pass-123")
    actor = service.authenticate_token(issued.token)

    assert admin is not None
    assert admin.role == "admin"
    assert actor.user.email == "admin@example.com"


def test_register_rejects_duplicate_email():
    service = build_service()

    service.register(email="user@example.com", password="secret-123")

    with pytest.raises(ValueError, match="该邮箱已注册，请直接登录。"):
        service.register(email="user@example.com", password="secret-456")


def test_authenticate_expired_token_deletes_token_record():
    from langchain_api.web_backend.auth.models import AccessTokenRecord, utc_now

    service = build_service()
    user = service.register(email="user@example.com", password="secret-123")
    issued = service.store.issue_access_token(
        user=user,
        raw_token="expired-token",
        expire_days=1,
    )

    with Session(service.store.engine) as session:
        record = session.exec(
            select(AccessTokenRecord).where(
                AccessTokenRecord.token_hash == issued.record.token_hash
            )
        ).one()
        record.expires_at = utc_now() - timedelta(seconds=1)
        session.add(record)
        session.commit()

    with pytest.raises(ValueError, match="登录状态已失效，请重新登录。"):
        service.authenticate_token(issued.token)

    with Session(service.store.engine) as session:
        deleted_record = session.exec(
            select(AccessTokenRecord).where(
                AccessTokenRecord.token_hash == issued.record.token_hash
            )
        ).first()

    assert deleted_record is None


def test_reconcile_access_tokens_clamps_legacy_expiry_to_one_day():
    from langchain_api.web_backend.auth.models import AccessTokenRecord, utc_now

    service = build_service(token_expire_days=1)
    user = service.register(email="legacy@example.com", password="secret-123")
    issued = service.store.issue_access_token(
        user=user,
        raw_token="legacy-token",
        expire_days=30,
    )

    with Session(service.store.engine) as session:
        record = session.exec(
            select(AccessTokenRecord).where(
                AccessTokenRecord.token_hash == issued.record.token_hash
            )
        ).one()
        record.created_at = utc_now() - timedelta(hours=12)
        record.expires_at = record.created_at + timedelta(days=30)
        session.add(record)
        session.commit()

    service.store.reconcile_access_token_expiry(expire_days=1)

    with Session(service.store.engine) as session:
        updated_record = session.exec(
            select(AccessTokenRecord).where(
                AccessTokenRecord.token_hash == issued.record.token_hash
            )
        ).one()

    assert updated_record.expires_at == updated_record.created_at + timedelta(days=1)
