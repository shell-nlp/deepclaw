import pytest


def build_service():
    from langchain_api.auth.service import AuthService
    from langchain_api.auth.store import AuthStore

    return AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        token_expire_days=30,
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
