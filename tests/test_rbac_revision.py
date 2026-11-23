"""策略版本号与多进程重载回归测试。"""

import asyncio

import pytest

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import enforcer
from deepclaw.web_backend.auth.rbac import store as store_module
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore


@pytest.fixture
def revision_store(tmp_path, monkeypatch):
    """构造隔离的策略存储并重置授权引擎缓存。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", True)
    db_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    store = RbacPolicyStore(db_url, db_url)
    monkeypatch.setattr(store_module, "_store", store)
    enforcer._enforcer = None
    enforcer._last_revision = 0
    yield store
    enforcer._enforcer = None
    enforcer._last_revision = 0


def test_revision_bump_reloads_enforcer_for_other_processes(revision_store):
    """另一个进程写入策略后，版本号变化会触发本进程重载。

    Args:
        revision_store: 隔离的策略存储。
    """

    async def verify() -> None:
        """执行版本号与重载的异步回归。

        Args:
            无。
        """
        store = revision_store
        await store.ensure_schema()
        actor = CurrentActor(is_guest=False, user_id="user_1", email=None, role="user")

        await store.add_policy("user", "/api/alpha/*", "read")
        first_revision = await store.current_revision()
        assert first_revision >= 1
        assert enforcer.is_allowed(actor, path="/api/alpha/1", action="read") is True
        assert enforcer.is_allowed(actor, path="/api/beta/1", action="read") is False

        # 模拟另一个 worker 写入：版本号增长，但本进程内存策略仍是旧的。
        await store.add_policy("user", "/api/beta/*", "read")
        assert await store.current_revision() > first_revision
        assert enforcer.is_allowed(actor, path="/api/beta/1", action="read") is False

        assert await enforcer.refresh_enforcer_if_stale() is True
        assert enforcer.is_allowed(actor, path="/api/beta/1", action="read") is True

        # 版本号未变化时不应重复重建。
        assert await enforcer.refresh_enforcer_if_stale() is False

    asyncio.run(verify())


def test_revision_skipped_when_store_disabled(tmp_path, monkeypatch):
    """关闭数据库策略时不轮询版本号。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", False)
    assert asyncio.run(enforcer.refresh_enforcer_if_stale()) is False
