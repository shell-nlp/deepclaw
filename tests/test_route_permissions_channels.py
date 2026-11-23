"""渠道与设备路由 Casbin 权限守卫回归测试。"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deepclaw.settings import settings
from deepclaw.web_backend.auth.rbac import enforcer
from deepclaw.web_backend.auth.rbac import store as store_module
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore
from deepclaw.web_backend.auth.security import generate_access_token
from deepclaw.web_backend.auth.service import AuthService, get_auth_service
from deepclaw.web_backend.auth.store import AuthStore
from deepclaw.web_backend.channels.router import router as channels_router
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store
from deepclaw.web_backend.devices.router import router as devices_router
from deepclaw.web_backend.devices.store import DeviceStore, get_device_store


@pytest.fixture
def route_client(tmp_path, monkeypatch):
    """构造隔离的认证、RBAC、渠道与设备数据库以及 ASGI 应用。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", True)
    rbac_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    auth_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    policy_store = RbacPolicyStore(rbac_url, auth_url)
    monkeypatch.setattr(store_module, "_store", policy_store)
    enforcer._enforcer = None
    auth_store = AuthStore(auth_url)
    auth_service = AuthService(
        store=auth_store,
        admin_username=None,
        admin_password=None,
        token_expire_days=1,
    )
    channel_store = ChannelStore(f"sqlite:///{(tmp_path / 'channels.db').as_posix()}")
    device_store = DeviceStore(f"sqlite:///{(tmp_path / 'devices.db').as_posix()}")
    app = FastAPI()
    app.include_router(channels_router)
    app.include_router(devices_router)
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_channel_store] = lambda: channel_store
    app.dependency_overrides[get_device_store] = lambda: device_store
    yield app, policy_store, auth_store, channel_store, device_store
    enforcer._enforcer = None


def test_channel_read_role_cannot_access_devices(route_client):
    """仅授予渠道读权限的自定义角色可读绑定但不能查看设备。

    Args:
        route_client: 隔离应用与后端存储。
    """
    app, policy_store, auth_store, channel_store, device_store = route_client

    async def verify() -> None:
        """使用真实访问令牌验证渠道与设备路由的权限动作映射。

        Args:
            无。
        """
        try:
            await policy_store.ensure_catalog()
            await policy_store.create_catalog_role("channel_reader", "渠道只读", "只能查看渠道绑定")
            await policy_store.replace_catalog_permissions(
                "channel_reader",
                [("/api/channels/*", "read")],
            )
            user = await auth_store.create_user(
                username="reader",
                password_hash="x",
                role="channel_reader",
            )
            issued = await auth_store.issue_access_token(
                user=user,
                raw_token=generate_access_token(),
                expire_days=1,
            )
            headers = {"Authorization": f"Bearer {issued.token}"}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                bindings = await client.get("/api/channels/bindings", headers=headers)
                assert bindings.status_code == 200, bindings.text
                assert bindings.json()["items"] == []
                denied_action = await client.post(
                    "/api/channels/jobs/missing/actions",
                    headers=headers,
                    json={"action": "close"},
                )
                assert denied_action.status_code == 403, denied_action.text
                devices = await client.get("/api/devices", headers=headers)
                assert devices.status_code == 403, devices.text
                assert (await client.get("/api/devices")).status_code == 403
                assert (await client.get("/api/channels/bindings")).status_code == 200
        finally:
            await channel_store.engine.dispose()
            await device_store.engine.dispose()
            await auth_store.engine.dispose()
            await policy_store.engine.dispose()

    asyncio.run(verify())
