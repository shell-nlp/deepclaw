"""角色权限目录接口与服务端规则映射回归测试。"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor
from deepclaw.web_backend.auth.rbac import enforcer
from deepclaw.web_backend.auth.rbac import store as store_module
from deepclaw.web_backend.auth.rbac.permissions import (
    allowed_permission_pairs,
    list_permission_definitions,
)
from deepclaw.web_backend.auth.rbac.router import router
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore


@pytest.fixture
def permission_client(tmp_path, monkeypatch):
    """构造隔离的权限目录 ASGI 客户端。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", True)
    rbac_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    auth_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    store = RbacPolicyStore(rbac_url, auth_url)
    monkeypatch.setattr(store_module, "_store", store)
    enforcer._enforcer = None
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_authenticated_actor] = lambda: CurrentActor(
        is_guest=False, user_id="root", email=None, role="admin"
    )
    yield app, store
    enforcer._enforcer = None


def test_permission_catalog_codes_and_rules_are_consistent():
    """权限代码唯一，且每项至少映射一条真实服务端规则。

    Args:
        无。
    """
    definitions = list_permission_definitions()
    assert definitions
    codes = [item.code for item in definitions]
    assert len(codes) == len(set(codes))
    for definition in definitions:
        assert definition.group
        assert definition.name
        assert definition.description
        assert definition.rules
        for rule in definition.rules:
            if rule.path.startswith("/agent/tools/"):
                assert rule.action == "use"
            else:
                assert rule.path.startswith("/api/")
                assert rule.action in {"read", "write"}


def test_permission_allowlist_covers_catalog_rules():
    """白名单包含全部目录规则，避免目录项无法保存。

    Args:
        无。
    """
    allowed = allowed_permission_pairs()
    for definition in list_permission_definitions():
        for rule in definition.rules:
            assert (rule.path, rule.action) in allowed


def test_permission_catalog_endpoint_and_rejects_unknown_rules(permission_client):
    """接口返回目录；提交目录外规则时拒绝写入。

    Args:
        permission_client: 隔离 ASGI 应用与持久化存储。
    """

    async def verify() -> None:
        """执行权限目录接口异步回归。

        Args:
            无。
        """
        app, store = permission_client
        await store.ensure_catalog()
        await store.add_policy("admin", "/api/auth/rbac/*", "read")
        await store.add_policy("admin", "/api/auth/rbac/*", "write")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            catalog = await client.get("/api/auth/rbac/catalog/permissions")
            assert catalog.status_code == 200, catalog.text
            payload = catalog.json()["permissions"]
            assert {item["code"] for item in payload} == {
                item.code for item in list_permission_definitions()
            }

            created = await client.post(
                "/api/auth/rbac/catalog/roles",
                json={"id": "auditor", "name": "审核员", "description": "只读审核"},
            )
            assert created.status_code == 201, created.text

            rejected = await client.put(
                "/api/auth/rbac/catalog/roles/auditor/permissions",
                json={"permissions": [{"path": "/api/unknown/*", "action": "read"}]},
            )
            assert rejected.status_code == 422

            accepted = await client.put(
                "/api/auth/rbac/catalog/roles/auditor/permissions",
                json={"permissions": [{"path": "/api/auth/users/*", "action": "read"}]},
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["permissions"] == [
                {"path": "/api/auth/users/*", "action": "read"}
            ]

    asyncio.run(verify())
