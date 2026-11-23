"""角色目录 API 与持久化回归测试。"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor
from deepclaw.web_backend.auth.models import AuthUser
from deepclaw.web_backend.auth.rbac import enforcer
from deepclaw.web_backend.auth.rbac import store as store_module
from deepclaw.web_backend.auth.rbac.router import router
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore


@pytest.fixture
def catalog_client(tmp_path, monkeypatch):
    """构造隔离的 RBAC 与认证数据库以及 ASGI 客户端。

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


def test_catalog_crud_permissions_and_user_counts(catalog_client):
    """验证目录增改删、直接权限替换、用户数和在用限制。

    Args:
        catalog_client: 隔离 ASGI 应用与持久化存储。
    """

    async def verify() -> None:
        """执行目录功能异步回归。

        Args:
            无。
        """
        app, store = catalog_client
        await store.ensure_catalog()
        await store.add_policy("admin", "/api/auth/rbac/*", "read")
        await store.add_policy("admin", "/api/auth/rbac/*", "write")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            base = "/api/auth/rbac/catalog/roles"
            first = await client.get(base)
            assert first.status_code == 200
            assert {item["id"] for item in first.json()["roles"]} == {"admin", "user"}
            assert len(await store.list_policies()) == 2
            app.dependency_overrides[require_authenticated_actor] = lambda: CurrentActor(
                is_guest=False, user_id="alice", email=None, role="user"
            )
            enforcer._enforcer = None
            assert (await client.get(base)).status_code == 403
            assert (await client.post(base, json={"id": "blocked", "name": "拒绝"})).status_code == 403
            app.dependency_overrides[require_authenticated_actor] = lambda: CurrentActor(
                is_guest=False, user_id="root", email=None, role="admin"
            )
            enforcer._enforcer = None
            created = await client.post(base, json={"id": "reviewer", "name": "审核员", "description": "只读"})
            assert created.status_code == 201, created.text
            assert created.json()["permissions"] == []
            assert (await client.post(base, json={"id": "reviewer", "name": "重复"})).status_code == 409
            assert (await client.post(base, json={"id": "bad,role", "name": "无效"})).status_code == 422
            updated = await client.patch(base + "/reviewer", json={"name": "审阅人"})
            assert updated.json()["id"] == "reviewer"
            assert updated.json()["name"] == "审阅人"
            replaced = await client.put(
                base + "/reviewer/permissions",
                json={
                    "permissions": [
                        {"path": "/api/rag/*", "action": "read"},
                        {"path": "/api/rag/*", "action": "read"},
                    ]
                },
            )
            assert replaced.status_code == 200, replaced.text
            assert replaced.json()["permissions"] == [{"path": "/api/rag/*", "action": "read"}]
            assert (await client.put(base + "/reviewer/permissions", json={"permissions": []})).json()[
                "permissions"
            ] == []
            assert (await client.patch(base + "/admin", json={"name": "改"})).status_code == 409
            assert (await client.put(base + "/admin/permissions", json={"permissions": []})).status_code == 409
            assert (await client.delete(base + "/user")).status_code == 409
            assert (await client.patch(base + "/missing", json={"name": "无"})).status_code == 404
            assert (await client.delete(base + "/missing")).status_code == 404
            # 认证库独立于 SQLite RBAC 库，角色计数只读取 AuthUser.role。
            from deepclaw.utils.db import build_async_sessionmaker, create_async_engine_from_url
            from sqlmodel import SQLModel

            auth_engine = create_async_engine_from_url(store.auth_db_url)
            async with auth_engine.begin() as connection:
                await connection.run_sync(SQLModel.metadata.create_all)
            async with build_async_sessionmaker(auth_engine)() as session:
                session.add(AuthUser(user_id="alice", username="alice", role="reviewer", password_hash="x"))
                await session.commit()
            assert (
                next(role for role in (await client.get(base)).json()["roles"] if role["id"] == "reviewer")[
                    "user_count"
                ]
                == 1
            )
            assert (await client.delete(base + "/reviewer")).status_code == 409
            async with build_async_sessionmaker(auth_engine)() as session:
                user = (await session.exec(select(AuthUser).where(AuthUser.user_id == "alice"))).one()
                user.role = "user"
                session.add(user)
                await session.commit()
            await auth_engine.dispose()
            await store.add_policy("reviewer", "/api/agent/*", "read")
            await store.add_role("reviewer", "user")
            assert (await client.delete(base + "/reviewer")).status_code == 204
            assert not await store.role_exists("reviewer")
            assert not any(item.subject == "reviewer" for item in await store.list_policies())
            assert not any(item.child == "reviewer" for item in await store.list_roles())
        await store.engine.dispose()

    asyncio.run(verify())


def test_catalog_migrates_legacy_policy_without_reseeding(catalog_client):
    """验证旧 p/g 主体被纳入目录但不重复写入无用权限。

    Args:
        catalog_client: 隔离 ASGI 应用与持久化存储。
    """

    async def verify() -> None:
        """执行目录功能异步回归。

        Args:
            无。
        """
        _, store = catalog_client
        await store.ensure_schema()
        await store.add_policy("legacy", "/api/rag/*", "read")
        await store.add_role("staff", "legacy")
        await store.add_role("user_0123456789abcdef", "legacy")
        await store.ensure_catalog()
        assert await store.role_exists("legacy")
        assert {item.id for item in await store.list_catalog_roles()} == {"admin", "user", "legacy", "staff"}
        assert len(await store.list_policies()) == 1
        await store.ensure_catalog()
        assert len(await store.list_catalog_roles()) == 4
        await store.engine.dispose()

    asyncio.run(verify())


def test_catalog_exists_without_policy_database_mode(tmp_path, monkeypatch):
    """验证认证角色校验无需开启 RBAC 数据库策略模式。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", False)
    store = RbacPolicyStore(f"sqlite:///{(tmp_path / 'disabled.db').as_posix()}")

    async def verify() -> None:
        """校验默认目录角色并关闭连接池。

        Args:
            无。
        """
        assert await store.role_exists("user")
        assert await store.role_exists("admin")
        assert not await store.role_exists("unknown")
        await store.engine.dispose()

    asyncio.run(verify())
