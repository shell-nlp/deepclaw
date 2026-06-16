import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_client() -> TestClient:
    from deepclaw.web_backend.auth.router import create_auth_router
    from deepclaw.web_backend.auth.service import AuthService
    from deepclaw.web_backend.auth.store import AuthStore

    service = AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_email="admin@example.com",
        admin_password="admin-pass-123",
        token_expire_days=30,
    )
    asyncio.run(service.bootstrap_admin_if_needed())

    app = FastAPI()
    app.include_router(create_auth_router(service=service))
    return TestClient(app)


def test_guest_me_and_register_login_flow():
    client = build_client()

    guest = client.get("/api/auth/me")
    register = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "secret-123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "secret-123"},
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
        json={"email": "admin@example.com", "password": "admin-pass-123"},
    )
    token = login.json()["token"]
    response = client.post(
        "/api/auth/users/create",
        json={
            "email": "created@example.com",
            "password": "created-pass-123",
            "role": "user",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "created@example.com"


def test_admin_can_manage_user_accounts():
    client = build_client()

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-pass-123"},
    )
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/api/auth/users/create",
        json={"email": "managed@example.com", "password": "managed-pass-123", "role": "user"},
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
    assert any(item["email"] == "managed@example.com" for item in listed.json()["items"])
    assert role_updated.status_code == 200
    assert role_updated.json()["user"]["role"] == "admin"
    assert status_updated.status_code == 200
    assert status_updated.json()["user"]["is_active"] is False
    assert reset.status_code == 200

