import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_client() -> TestClient:
    from deepclaw.web_backend.auth.router import router as auth_router
    from deepclaw.web_backend.auth.service import AuthService, get_auth_service
    from deepclaw.web_backend.auth.store import AuthStore

    service = AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_username="admin",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )
    asyncio.run(service.bootstrap_admin_if_needed())

    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.include_router(auth_router)
    return TestClient(app)


def test_guest_me_and_register_login_flow():
    client = build_client()

    guest = client.get("/api/auth/me")
    register = client.post(
        "/api/auth/register",
        json={"username": "user", "password": "secret-123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "secret-123"},
    )

    assert guest.status_code == 200
    assert guest.json()["is_guest"] is True
    assert register.status_code == 200
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "user"


def test_admin_can_create_user():
    client = build_client()

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-pass-123"},
    )
    token = login.json()["token"]
    response = client.post(
        "/api/auth/users/create",
        json={
            "username": "created",
            "password": "created-pass-123",
            "role": "user",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "created"


def test_admin_can_manage_user_accounts():
    client = build_client()

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-pass-123"},
    )
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/api/auth/users/create",
        json={"username": "managed", "password": "managed-pass-123", "role": "user"},
        headers=headers,
    )
    user_id = create.json()["user"]["user_id"]

    listed = client.post("/api/auth/users/list", json={}, headers=headers)
    role_updated = client.post(
        "/api/auth/users/update-role",
        json={"user_id": user_id, "role": "admin"},
        headers=headers,
    )
    status_updated = client.post(
        "/api/auth/users/update-status",
        json={"user_id": user_id, "is_active": False},
        headers=headers,
    )
    reset = client.post(
        "/api/auth/users/reset-password",
        json={"user_id": user_id, "password": "reset-pass-123"},
        headers=headers,
    )

    assert listed.status_code == 200
    assert any(item["username"] == "managed" for item in listed.json()["items"])
    assert role_updated.status_code == 200
    assert role_updated.json()["user"]["role"] == "admin"
    assert status_updated.status_code == 200
    assert status_updated.json()["user"]["is_active"] is False
    assert reset.status_code == 200


def test_custom_role_token_uses_catalog_permissions(tmp_path, monkeypatch):
    from deepclaw.settings import settings
    from deepclaw.web_backend.auth.rbac import enforcer as enforcer_module
    from deepclaw.web_backend.auth.rbac import store as rbac_store_module
    from deepclaw.web_backend.auth.rbac.adapter import read_default_policy_file
    from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore
    from deepclaw.web_backend.auth.service import AuthService, get_auth_service
    from deepclaw.web_backend.auth.store import AuthStore

    auth_store = AuthStore("sqlite:///:memory:")
    rbac_store = RbacPolicyStore(
        f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}",
        auth_db_url="sqlite:///:memory:",
    )
    policies, roles = read_default_policy_file(enforcer_module.resolve_rbac_paths()[1])
    monkeypatch.setattr(rbac_store_module, "_store", rbac_store)
    service = AuthService(
        store=auth_store,
        admin_username="admin",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )

    async def seed():
        await rbac_store.ensure_schema()
        await rbac_store.seed(policies, roles)
        await rbac_store.ensure_catalog()
        await rbac_store.create_catalog_role("reviewer", "Reviewer", "Read user list")
        await rbac_store.replace_catalog_permissions(
            "reviewer", [("/api/auth/users/list", "read")]
        )
        await service.bootstrap_admin_if_needed()
        await service.create_user_as_admin(
            username="reviewer", password="reviewer-pass-123", role="reviewer"
        )

    asyncio.run(seed())
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", True)
    monkeypatch.setattr(rbac_store_module, "_store", rbac_store)
    monkeypatch.setattr(enforcer_module, "_enforcer", None)
    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: service
    from deepclaw.web_backend.auth.router import router as auth_router

    app.include_router(auth_router)
    client = TestClient(app)
    issued = client.post(
        "/api/auth/login",
        json={"username": "reviewer", "password": "reviewer-pass-123"},
    )
    headers = {"Authorization": f"Bearer {issued.json()['token']}"}
    me = client.get("/api/auth/me", headers=headers)
    listed = client.post("/api/auth/users/list", json={}, headers=headers)

    assert issued.status_code == 200
    assert me.json()["role"] == "reviewer"
    assert {"path": "/api/auth/users/list", "action": "read"} in me.json()["permissions"]
    assert listed.status_code == 200
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", False)
    monkeypatch.setattr(rbac_store_module, "_store", None)
    monkeypatch.setattr(enforcer_module, "_enforcer", None)


def test_last_active_admin_cannot_be_demoted_or_disabled():
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore
    from deepclaw.web_backend.common.errors import BusinessRuleError

    service = AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_username="admin",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )

    async def check():
        admin = await service.bootstrap_admin_if_needed()
        with pytest.raises(BusinessRuleError, match="启用中的管理员"):
            await service.update_user_role(user_id=admin.user_id, role="user")
        with pytest.raises(BusinessRuleError, match="启用中的管理员"):
            await service.update_user_status(user_id=admin.user_id, is_active=False)
        assert admin.role == "admin"
        assert admin.is_active is True

    asyncio.run(check())

