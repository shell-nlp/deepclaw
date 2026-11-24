"""认证访问策略回归测试：游客开关、注册开关、登录失败锁定与旧库迁移。"""

import asyncio
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.settings import settings
from deepclaw.web_backend.auth.service import AuthService
from deepclaw.web_backend.auth.store import AuthStore
from deepclaw.web_backend.common.errors import BusinessRuleError


def _build_service(**overrides) -> AuthService:
    """构造基于内存库的认证服务并自举管理员。

    Args:
        overrides: 覆盖 AuthService 构造参数。

    Returns:
        AuthService: 已自举管理员的服务实例。
    """
    service = AuthService(
        store=AuthStore("sqlite:///:memory:"),
        admin_username="admin",
        admin_password="admin-pass-123",
        token_expire_days=30,
        **overrides,
    )
    asyncio.run(service.bootstrap_admin_if_needed())
    return service


def _build_client(service: AuthService) -> TestClient:
    """构造只挂载认证路由的测试客户端。

    Args:
        service: 认证服务实例。

    Returns:
        TestClient: 注入该服务的测试客户端。
    """
    from deepclaw.web_backend.auth.router import router as auth_router
    from deepclaw.web_backend.auth.service import get_auth_service

    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.include_router(auth_router)
    return TestClient(app)


def test_guest_denied_when_guest_access_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_GUEST_ACCESS", False)
    client = _build_client(_build_service())

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录后再使用该功能。"


def test_auth_config_reports_current_switches(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_GUEST_ACCESS", False)
    monkeypatch.setattr(settings, "AUTH_ALLOW_REGISTRATION", False)
    client = _build_client(_build_service())

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "allow_guest": False,
        "allow_registration": False,
    }


def test_register_rejected_when_registration_disabled():
    service = _build_service(allow_registration=False)

    with pytest.raises(BusinessRuleError, match="关闭公开注册"):
        asyncio.run(service.register(username="new-user", password="secret-123"))


def test_login_locks_account_after_repeated_failures():
    service = _build_service(max_login_attempts=3, login_lock_minutes=15)

    async def check():
        for _ in range(2):
            with pytest.raises(BusinessRuleError, match="用户名或密码错误"):
                await service.login(username="admin", password="wrong-pass")
        with pytest.raises(BusinessRuleError, match="锁定 15 分钟"):
            await service.login(username="admin", password="wrong-pass")
        with pytest.raises(BusinessRuleError, match="临时锁定"):
            await service.login(username="admin", password="admin-pass-123")
        user = await service.store.get_user_by_username("admin")
        assert user is not None
        assert user.locked_until is not None

    asyncio.run(check())


def test_successful_login_resets_failure_counter():
    service = _build_service(max_login_attempts=5)

    async def check():
        with pytest.raises(BusinessRuleError, match="用户名或密码错误"):
            await service.login(username="admin", password="wrong-pass")
        issued = await service.login(username="admin", password="admin-pass-123")
        user = await service.store.get_user_by_username("admin")
        assert issued.user.user_id == user.user_id
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    asyncio.run(check())


def test_legacy_schema_adds_login_lock_columns(tmp_path):
    db_path = tmp_path / "auth.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE authuser ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "user_id VARCHAR NOT NULL UNIQUE, "
            "username VARCHAR UNIQUE, "
            "email VARCHAR, "
            "password_hash VARCHAR NOT NULL, "
            "role VARCHAR NOT NULL, "
            "is_active BOOLEAN NOT NULL, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL"
            ")"
        )

    store = AuthStore(f"sqlite:///{db_path.as_posix()}")
    asyncio.run(store._ensure_init())

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(authuser)")
        }
    assert {"failed_login_attempts", "locked_until"} <= columns
