from fastapi import HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import (
    is_allowed,
    reload_enforcer,
    require_permission,
    resolve_rbac_paths,
)
from deepclaw.web_backend.channels.common import is_admin


import pytest


@pytest.fixture(autouse=True)
def reset_rbac_state(monkeypatch):
    """每个测试前把授权引擎恢复到默认配置，避免测试间互相污染。

    Args:
        monkeypatch: Pytest 的属性替换工具。
    """
    from deepclaw.settings import settings as app_settings
    from deepclaw.web_backend.auth.rbac import enforcer as enforcer_module
    from deepclaw.web_backend.auth.rbac import store as store_module

    monkeypatch.setattr(app_settings, "RBAC_STORE_ENABLED", False)
    store_module._store = None
    enforcer_module._enforcer = None
    yield
    store_module._store = None
    enforcer_module._enforcer = None


def make_actor(user_id: str, role: str = "user", *, guest: bool = False) -> CurrentActor:
    """构造测试用鉴权主体。

    Args:
        user_id: 主体用户 ID。
        role: 主体角色。
        guest: 是否为游客。

    Returns:
        CurrentActor: 测试主体。
    """
    if guest:
        return CurrentActor(is_guest=True, user_id=None, email=None, role="guest")
    return CurrentActor(is_guest=False, user_id=user_id, email=f"{user_id}@example.com", role=role)


def test_policy_files_are_resolvable() -> None:
    """验证模型与策略文件都能解析到实际文件。

    Args:
        无。
    """
    model_path, policy_path = resolve_rbac_paths()
    assert model_path.is_file()
    assert policy_path.is_file()


def test_enforcer_loads_default_roles_and_rules() -> None:
    """验证默认策略包含内置角色和继承关系。

    Args:
        无。
    """
    reload_enforcer()
    from deepclaw.web_backend.auth.rbac.enforcer import get_enforcer

    enforcer = get_enforcer()
    roles = {child for child, _ in enforcer.get_grouping_policy()}
    assert "admin" in roles
    assert len(enforcer.get_policy()) >= 10


def test_owner_can_read_own_resource_but_not_others() -> None:
    """验证普通用户只能访问自己归属的资源。

    Args:
        无。
    """
    alice = make_actor("alice")
    path = "/api/rag/knowledge-bases/detail"
    assert is_allowed(alice, path=path, action="read", owner="alice")
    assert not is_allowed(alice, path=path, action="read", owner="bob")


def test_admin_bypasses_ownership_but_keeps_own_permissions() -> None:
    """验证管理员可跨用户访问，且不会获得策略外的权限。

    Args:
        无。
    """
    admin = make_actor("bob", "admin")
    assert is_allowed(
        admin,
        path="/api/rag/knowledge-bases/detail",
        action="read",
        owner="alice",
    )
    assert not is_allowed(admin, path="/api/rag/knowledge-bases/detail", action="delete")


def test_user_cannot_access_admin_endpoints() -> None:
    """验证普通用户无法访问管理员接口。

    Args:
        无。
    """
    user = make_actor("alice")
    admin = make_actor("bob", "admin")
    assert not is_allowed(user, path="/api/auth/users/list", action="read")
    assert is_allowed(admin, path="/api/auth/users/list", action="read")


def test_guest_has_no_protected_permissions() -> None:
    """验证游客没有受保护接口权限。

    Args:
        无。
    """
    guest = make_actor("", guest=True)
    assert not is_allowed(guest, path="/api/devices", action="read")
    assert not is_allowed(guest, path="/api/auth/users/list", action="read")


def test_is_admin_uses_policy_instead_of_role_name() -> None:
    """验证渠道模块的管理员判定走 Casbin 策略。

    Args:
        无。
    """
    assert is_admin(make_actor("bob", "admin")) is True
    assert is_admin(make_actor("alice")) is False
    assert is_admin(make_actor("", guest=True)) is False


def test_require_permission_rejects_user_and_accepts_admin() -> None:
    """验证权限依赖对普通用户拒绝、对管理员放行。

    Args:
        无。
    """
    dependency = require_permission("/api/auth/users/list", "read")

    async def run() -> None:
        """执行异步依赖校验。

        Args:
            无。
        """
        with pytest.raises(HTTPException) as rejected:
            await dependency(make_actor("alice"))
        assert rejected.value.status_code == 403
        actor = await dependency(make_actor("bob", "admin"))
        assert actor.user_id == "bob"

    __import__("asyncio").run(run())


def test_require_permission_resolves_owner() -> None:
    """验证权限依赖可按解析出的归属放行。

    Args:
        无。
    """
    dependency = require_permission(
        "/api/rag/knowledge-bases/detail",
        "read",
        owner=lambda actor: "alice",
    )

    async def run() -> None:
        """执行异步依赖校验。

        Args:
            无。
        """
        actor = await dependency(make_actor("alice"))
        assert actor.user_id == "alice"
        with pytest.raises(HTTPException):
            await dependency(make_actor("carol"))

    __import__("asyncio").run(run())


def test_policy_store_seeds_and_roundtrips(tmp_path, monkeypatch):
    """验证策略落库、读取与删除的完整往返。

    Args:
        tmp_path: Pytest 提供的临时目录。
        monkeypatch: Pytest 的属性替换工具。
    """
    import asyncio

    from deepclaw.web_backend.auth.rbac import enforcer as enforcer_module
    from deepclaw.web_backend.auth.rbac import store as store_module
    from deepclaw.web_backend.auth.rbac.adapter import (
        bootstrap_policy_store,
        read_default_policy_file,
    )

    db_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    store = store_module.RbacPolicyStore(db_url)
    store_module._store = store
    policies, roles = read_default_policy_file(enforcer_module.resolve_rbac_paths()[1])

    async def run_repository() -> None:
        """执行策略入库与删除流程。

        Args:
            无。
        """
        await bootstrap_policy_store(store, policies, roles)
        stored = await store.list_policies()
        assert len(stored) == len(policies)
        assert len(await store.list_roles()) == len(roles)
        await store.add_policy("user", "/api/devices/probe", "read")
        assert any(rule.path == "/api/devices/probe" for rule in await store.list_policies())
        assert await store.delete_policy("user", "/api/devices/probe", "read")
        assert not any(rule.path == "/api/devices/probe" for rule in await store.list_policies())

    asyncio.run(run_repository())
    store_module._store = None
    enforcer_module.reload_enforcer()


def test_database_policy_change_takes_effect_on_reload(tmp_path):
    """验证策略新增与删除后重载立即生效。

    Args:
        tmp_path: Pytest 提供的临时目录。
    """
    import asyncio

    from deepclaw.web_backend.auth.rbac import enforcer as enforcer_module
    from deepclaw.web_backend.auth.rbac import store as store_module
    from deepclaw.web_backend.auth.rbac.adapter import (
        bootstrap_policy_store,
        read_default_policy_file,
    )

    db_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    store = store_module.RbacPolicyStore(db_url)
    store_module._store = store
    policies, roles = read_default_policy_file(enforcer_module.resolve_rbac_paths()[1])
    asyncio.run(bootstrap_policy_store(store, policies, roles))

    alice = make_actor("alice")
    probe_path = "/api/rbac-probe/resource"
    monkeypatch_enabled = enforcer_module.settings.RBAC_STORE_ENABLED
    enforcer_module.settings.RBAC_STORE_ENABLED = True
    try:
        enforcer_module.reload_enforcer()
        assert not enforcer_module.is_allowed(alice, path=probe_path, action="read")

        asyncio.run(store.add_policy("user", probe_path, "read"))
        enforcer_module.reload_enforcer()
        assert enforcer_module.is_allowed(alice, path=probe_path, action="read")

        asyncio.run(store.delete_policy("user", probe_path, "read"))
        enforcer_module.reload_enforcer()
        assert not enforcer_module.is_allowed(alice, path=probe_path, action="read")
    finally:
        enforcer_module.settings.RBAC_STORE_ENABLED = monkeypatch_enabled
        store_module._store = None
        enforcer_module.reload_enforcer()
