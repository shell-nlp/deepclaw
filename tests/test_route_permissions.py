"""知识库与技能路由 Casbin 权限守卫回归测试。"""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deepclaw.settings import settings
from deepclaw.web_backend.auth.rbac import enforcer
from deepclaw.web_backend.auth.rbac import store as store_module
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore
from deepclaw.web_backend.auth.security import hash_password
from deepclaw.web_backend.auth.service import AuthService, get_auth_service
from deepclaw.web_backend.auth.store import AuthStore
from deepclaw.web_backend.knowledge_bases import service as knowledge_bases_service
from deepclaw.web_backend.knowledge_bases.router import router as knowledge_bases_router
from deepclaw.web_backend.knowledge_bases.service import (
    KnowledgeBaseRecord,
    PaginatedKnowledgeBaseResponse,
)
from deepclaw.web_backend.skills.router import router as skills_router
from deepclaw.web_backend.skills.service import (
    SkillListResponse,
    SkillRecord,
    skill_manager,
)


class FakeKnowledgeBaseManager:
    """不触碰数据库与向量库的知识库管理器替身。"""

    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []

    async def search_knowledge_bases(
        self,
        user_id: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedKnowledgeBaseResponse:
        """返回空的知识库分页结果。

        Args:
            user_id: 归属用户 ID。
            search: 搜索关键字。
            page: 页码。
            page_size: 每页数量。
        """
        return PaginatedKnowledgeBaseResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
        )

    async def create_knowledge_base(
        self,
        user_id: str,
        name: str,
        description: str = "",
    ) -> KnowledgeBaseRecord:
        """记录创建参数并返回最小可用的知识库记录。

        Args:
            user_id: 归属用户 ID。
            name: 知识库名称。
            description: 知识库描述。
        """
        self.created.append(
            {"user_id": user_id, "name": name, "description": description}
        )
        return KnowledgeBaseRecord(
            knowledge_base_id="kb-1",
            user_id=user_id,
            name=name,
            description=description,
            passage_index="kb-1_passage",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )


def _fake_list_skills(*, search: str = "") -> SkillListResponse:
    """返回固定的技能列表，避免测试读取真实工作区。

    Args:
        search: 搜索关键字，测试中忽略。
    """
    return SkillListResponse(
        items=[
            SkillRecord(
                skill_name="demo",
                path="demo",
                description="demo",
                file_count=1,
                created_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:00",
            )
        ],
        total=1,
    )


@pytest.fixture
def guarded_client(tmp_path, monkeypatch):
    """构造带隔离 RBAC 策略、真实令牌与假管理器的 ASGI 应用。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 配置替换器。
    """
    monkeypatch.setattr(settings, "RBAC_STORE_ENABLED", True)
    rbac_url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    auth_url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    rbac_store = RbacPolicyStore(rbac_url, auth_url)
    auth_store = AuthStore(auth_url)
    service = AuthService(
        store=auth_store,
        admin_username=None,
        admin_password=None,
        token_expire_days=1,
    )
    monkeypatch.setattr(store_module, "_store", rbac_store)
    enforcer._enforcer = None
    monkeypatch.setattr(
        knowledge_bases_service,
        "knowledge_base_manager",
        FakeKnowledgeBaseManager(),
    )
    monkeypatch.setattr(skill_manager, "list_skills", _fake_list_skills)
    app = FastAPI()
    app.include_router(knowledge_bases_router)
    app.include_router(skills_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    yield app, rbac_store, auth_store, service
    app.dependency_overrides.clear()
    enforcer._enforcer = None


def test_guest_and_read_only_role_knowledge_base_routes(guarded_client):
    """验证只读角色可读不可写、游客读写放行。

    Args:
        guarded_client: 隔离的 ASGI 应用与存储。
    """

    async def verify() -> None:
        """执行真实令牌与游客请求的异步回归。

        Args:
            无。
        """
        app, rbac_store, auth_store, service = guarded_client
        await rbac_store.ensure_catalog()
        await rbac_store.add_policy("reader", "/api/rag/*", "read")
        await auth_store.create_user(
            username="reader",
            password_hash=hash_password("reader-pass-123"),
            role="reader",
        )
        issued = await service.login(username="reader", password="reader-pass-123")
        enforcer._enforcer = None
        headers = {"Authorization": f"Bearer {issued.token}"}
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            listed = await client.post(
                "/api/rag/knowledge-bases/list",
                json={"user_id": "reader"},
                headers=headers,
            )
            assert listed.status_code == 200, listed.text
            assert listed.json()["items"] == []
            created = await client.post(
                "/api/rag/knowledge-bases/create",
                json={"user_id": "reader", "name": "demo", "description": ""},
                headers=headers,
            )
            assert created.status_code == 403, created.text
            denied_skills = await client.post(
                "/api/agent/skills/list",
                json={},
                headers=headers,
            )
            assert denied_skills.status_code == 403, denied_skills.text

            guest_list = await client.post(
                "/api/rag/knowledge-bases/list",
                json={"user_id": "guest"},
            )
            assert guest_list.status_code == 200, guest_list.text
            guest_create = await client.post(
                "/api/rag/knowledge-bases/create",
                json={"user_id": "guest", "name": "guest-kb", "description": ""},
            )
            assert guest_create.status_code == 200, guest_create.text
            assert guest_create.json()["user_id"] == "guest"
            guest_skills = await client.post("/api/agent/skills/list", json={})
            assert guest_skills.status_code == 200, guest_skills.text

        await rbac_store.engine.dispose()
        await auth_store.engine.dispose()

    asyncio.run(verify())


def test_workspace_permissions_apply_to_custom_roles(guarded_client, monkeypatch, tmp_path):
    """验证默认策略回填和自定义角色的聊天、定时任务、MCP 权限。

    Args:
        guarded_client: 隔离的应用与身份存储。
        monkeypatch: 替换测试用的任务和运行存储。
        tmp_path: 临时数据库目录。
    """
    from deepclaw.middleware.cron.schedule_store import ScheduleStore
    from deepclaw.web_backend import schedules
    from deepclaw.web_backend.agent.run_store import InMemoryRunStore
    from deepclaw.web_backend.agui.router import get_agui_run_store, router as agui_router
    from deepclaw.web_backend.auth import service as auth_service_module
    from deepclaw.web_backend.auth.rbac.adapter import bootstrap_policy_store, read_default_policy_file
    from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission
    from deepclaw.web_backend.auth.rbac.router import _catalog_response

    async def verify():
        """使用真实令牌与 Casbin 检查权限，结束后释放测试连接。

        Args:
            无。
        """
        app, rbac_store, auth_store, service = guarded_client
        tasks = ScheduleStore(f"sqlite:///{(tmp_path / 'schedules.db').as_posix()}")
        monkeypatch.setattr(schedules, "get_schedule_store", lambda: tasks)
        monkeypatch.setattr(auth_service_module, "get_auth_service", lambda: service)
        app.include_router(agui_router)
        app.include_router(schedules.router)
        runs = InMemoryRunStore()
        app.dependency_overrides[get_agui_run_store] = lambda: runs
        try:
            await rbac_store.ensure_catalog()
            await rbac_store.add_policy("reader", "/api/agui/*", "read")
            await rbac_store.add_policy("reader", "/api/schedules", "read")
            _, policy_path = enforcer.resolve_rbac_paths()
            policies, roles = read_default_policy_file(policy_path)
            await bootstrap_policy_store(rbac_store, policies, roles)
            reader = await auth_store.create_user(
                username="reader", password_hash=hash_password("reader-pass-123"), role="reader",
            )
            issued = await service.login(username="reader", password="reader-pass-123")
            headers = {"Authorization": f"Bearer {issued.token}"}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                assert (await client.get("/api/agui/threads", headers=headers)).status_code == 200
                assert (await client.delete("/api/agui/threads/missing", headers=headers)).status_code == 403
                assert (await client.get("/api/schedules", headers=headers)).status_code == 200
                assert (await client.post("/api/schedules", headers=headers, json={
                    "name": "test", "content": "test", "interval_seconds": 10,
                })).status_code == 403
            assert not await agent_has_permission(reader.user_id, "/agent/tools/mcp", "use")
            await rbac_store.add_policy("reader", "/agent/tools/mcp", "use")
            enforcer.reload_enforcer()
            assert await agent_has_permission(reader.user_id, "/agent/tools/mcp", "use")
            assert any(
                (rule.path, rule.action) == ("/api/schedules", "write")
                for role in (await _catalog_response(rbac_store)).roles if role.id == "admin"
                for rule in role.permissions
            )
        finally:
            await tasks.engine.dispose()
            await rbac_store.engine.dispose()
            await auth_store.engine.dispose()

    asyncio.run(verify())
