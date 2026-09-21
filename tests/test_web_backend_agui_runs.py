import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.agui.router import (
    get_agent_runtime_registry,
    get_agui_run_store,
    get_checkpointer,
    get_langgraph_store,
    router as agui_router,
)
from deepclaw.web_backend.agent.run_store import InMemoryRunStore, RunState
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_schemas import AgUiRunRequest


class FakeRunManager:
    """测试用统一 AG-UI Run 管理器。"""

    def __init__(self):
        self.created = None
        self.resumed = None

    async def create(self, payload):
        """记录创建请求。

        Args:
            payload: AG-UI 输入。
        """
        self.created = payload
        return {
            "runId": payload.run_id,
            "threadId": payload.thread_id,
            "agentId": payload.agent_id or "agent",
            "status": "queued",
        }

    async def continue_run(self, run_id, payload, user_id=None):
        """记录恢复请求。

        Args:
            run_id: Run ID。
            payload: AG-UI 输入。
            user_id: 当前用户 ID。
        """
        self.resumed = (run_id, payload, user_id)
        return {
            "runId": run_id,
            "threadId": payload.thread_id,
            "agentId": payload.agent_id or "agent",
            "status": "queued",
        }


class FakeRuntimeRegistry:
    """测试用智能体运行时注册表。"""

    def __init__(self, manager):
        self.manager = manager

    async def get_graph(self, request, spec, checkpointer, store):
        """返回空图占位对象。

        Args:
            request: 当前请求。
            spec: 智能体定义。
            checkpointer: 检查点存储。
            store: 长期存储。
        """
        return object()

    async def get_manager(self, request, spec, graph, run_store):
        """返回测试 Run 管理器。

        Args:
            request: 当前请求。
            spec: 智能体定义。
            graph: 图对象。
            run_store: Run 存储。
        """
        return self.manager


def build_client(*, manager=None, store=None):
    """构建统一 AG-UI 测试客户端。

    Args:
        manager: 可选测试 Run 管理器。
        store: 可选 Run 存储。
    """
    app = FastAPI()
    app.include_router(agui_router)
    fake_manager = manager or FakeRunManager()
    run_store = store or InMemoryRunStore()
    app.dependency_overrides[get_agent_runtime_registry] = lambda: FakeRuntimeRegistry(
        fake_manager
    )
    app.dependency_overrides[get_agui_run_store] = lambda: run_store
    app.dependency_overrides[get_checkpointer] = lambda: None
    app.dependency_overrides[get_langgraph_store] = lambda: None
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        is_guest=True,
        user_id=None,
        email=None,
        role="guest",
    )
    return TestClient(app), fake_manager, run_store


def payload(run_id="run-1", agent_id="rag"):
    """构造最小 AgUiRunRequest。

    Args:
        run_id: Run ID。
        agent_id: 智能体 ID。
    """
    return {
        "agentId": agent_id,
        "threadId": "thread-1",
        "runId": run_id,
        "state": {"deep_thinking": True, "user_id": "spoofed"},
        "messages": [{"id": "message-1", "role": "user", "content": "hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def create_run_state(*, agent_id="rag", status="finished"):
    """创建测试 Run 状态。

    Args:
        agent_id: 智能体 ID。
        status: Run 状态。
    """
    request = AgUiRunRequest.model_validate(payload(agent_id=agent_id))
    return RunState(
        run_id=request.run_id,
        thread_id=request.thread_id,
        input=request,
        owner_user_id="guest",
        agent_id=agent_id,
        status=status,
    )


def test_list_agents_returns_agent_summaries():
    """验证智能体列表接口。"""
    client, _, _ = build_client()

    response = client.get("/api/agui/agents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == "agent"
    assert body["items"][0]["default"] is True
    assert {item["id"] for item in body["items"]} == {"agent", "rag"}


def test_create_run_uses_top_level_agent_id_and_trusted_actor():
    """验证创建 Run 时使用顶层 agentId 并覆盖客户端 user_id。"""
    client, manager, _ = build_client()

    response = client.post("/api/agui/runs", json=payload(agent_id="rag"))

    assert response.status_code == 202
    assert response.json()["agentId"] == "rag"
    assert manager.created.agent_id == "rag"
    assert manager.created.state["user_id"] == "guest"
    assert manager.created.state["deep_thinking"] is True


def test_create_run_rejects_unknown_agent():
    """验证未知 agentId 返回 422。"""
    client, _, _ = build_client()

    response = client.post("/api/agui/runs", json=payload(agent_id="missing"))

    assert response.status_code == 422


def test_run_snapshot_events_resume_and_cancel():
    """验证 Run Snapshot、事件、恢复和取消端点。"""
    store = InMemoryRunStore()

    async def seed():
        state = create_run_state(agent_id="rag", status="finished")
        assert await store.create_run(state)
        await store.append_event(
            "run-1",
            'data: {"type":"RUN_STARTED"}\n\n',
        )

    asyncio.run(seed())
    client, manager, _ = build_client(store=store)

    snapshot = client.get("/api/agui/runs/run-1")
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "finished"
    assert snapshot.json()["agentId"] == "rag"

    events = client.get("/api/agui/runs/run-1/events")
    assert events.status_code == 200
    assert "RUN_STARTED" in events.text

    resumed = client.post(
        "/api/agui/runs/run-1/resume",
        json=payload(agent_id="rag"),
    )
    assert resumed.status_code == 202
    assert manager.resumed[0] == "run-1"

    cancelled = client.post("/api/agui/runs/run-1/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["runId"] == "run-1"


def test_resume_rejects_agent_switch():
    """验证 resume 不允许切换 Run 的 agentId。"""
    store = InMemoryRunStore()

    async def seed():
        assert await store.create_run(create_run_state(agent_id="rag"))

    asyncio.run(seed())
    client, _, _ = build_client(store=store)

    response = client.post(
        "/api/agui/runs/run-1/resume",
        json=payload(agent_id="agent"),
    )

    assert response.status_code == 409
