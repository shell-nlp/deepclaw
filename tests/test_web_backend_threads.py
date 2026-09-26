import asyncio
from types import SimpleNamespace

from ag_ui.core import RunAgentInput
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from deepclaw.agent_registry import AgentRegistry
from deepclaw.web_backend.agui.router import (
    get_agent_runtime_cache,
    get_agui_run_store,
    get_checkpointer,
    router as agui_router,
)
from deepclaw.web_backend.agent.run_manager import AgentRunManager
from deepclaw.web_backend.agent.run_store import (
    AgUiCheckpointRecord,
    InMemoryRunStore,
    PERSISTENT_THREAD_EXPIRES_AT,
    RunState,
    SqlRunStore,
    ThreadState,
    restore_threads_from_checkpoints,
)
from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.common.agui_runs import _collect_message_created_at


class FakeThreadStore:
    """测试用 Thread/Run 存储。"""

    async def list_runs_by_thread(
        self,
        thread_id,
        user_id=None,
        *,
        agent_id=None,
        limit=100,
    ):
        """返回固定 Thread Run 列表。

        Args:
            thread_id: Thread ID。
            user_id: 当前用户 ID。
            agent_id: 可选智能体 ID。
            limit: 最大返回数量。
        """
        if thread_id != "thread-1" or user_id != "guest":
            return None
        if agent_id is not None and agent_id != "agent":
            return []
        return [
            SimpleNamespace(
                run_id="run-1",
                thread_id="thread-1",
                agent_id="agent",
                status="finished",
                last_event_id=1,
                created_at=1.0,
                updated_at=2.0,
                error=None,
            )
        ][:limit]

    async def list_threads(self, user_id, *, agent_id=None, limit=100):
        """返回固定 Thread 列表。

        Args:
            user_id: 当前用户 ID。
            agent_id: 可选智能体 ID。
            limit: 最大返回数量。
        """
        if user_id != "guest":
            return []
        if agent_id is not None and agent_id != "agent":
            return []
        return [
            ThreadState(
                thread_id="thread-1",
                owner_user_id="guest",
                agent_id="agent",
                title="测试标题",
            )
        ][:limit]

    async def get_thread(self, thread_id, user_id=None):
        """返回固定 Thread 状态。

        Args:
            thread_id: Thread ID。
            user_id: 当前用户 ID。
        """
        if thread_id != "thread-1" or user_id != "guest":
            return None
        return ThreadState(
            thread_id=thread_id,
            owner_user_id="guest",
            agent_id="agent",
        )

    async def create_thread(self, state):
        """模拟创建 Thread。

        Args:
            state: Thread 状态。
        """
        return True

    async def delete_thread(self, thread_id, user_id=None):
        """记录删除的 Thread。

        Args:
            thread_id: Thread ID。
            user_id: 当前用户 ID。
        """
        return thread_id == "thread-1" and user_id == "guest"


class FakeGraph:
    """测试用 LangGraph 图。"""

    async def aget_state(self, config):
        """返回固定图状态。

        Args:
            config: LangGraph 配置。
        """
        assert config == {"configurable": {"thread_id": "thread-1"}}
        return SimpleNamespace(
            values={
                "messages": [
                    SimpleNamespace(id="m1", content="测试标题"),
                    SimpleNamespace(id="m2", content="回答"),
                ]
            }
        )

    async def aget_state_history(self, config):
        """返回固定 checkpoint 历史，按时间从新到旧。

        Args:
            config: LangGraph 配置。
        """
        assert config == {"configurable": {"thread_id": "thread-1"}}
        yield SimpleNamespace(
            values={
                "messages": [
                    SimpleNamespace(id="m1", content="测试标题"),
                    SimpleNamespace(id="m2", content="回答"),
                ]
            },
            created_at="2026-09-22T00:00:02+00:00",
        )
        yield SimpleNamespace(
            values={"messages": [SimpleNamespace(id="m1", content="测试标题")]},
            created_at="2026-09-22T00:00:01+00:00",
        )


class FakeRuntimeRegistry:
    """测试用智能体运行时注册表。"""

    def __init__(self, graph):
        self.graph = graph

    async def get_graph(self, request, agent, checkpointer, store):
        """返回测试图。

        Args:
            request: 当前请求。
            agent: 智能体类。
            checkpointer: 检查点存储。
            store: 长期存储。
        """
        return self.graph


class FakeCheckpointer:
    """测试用检查点存储。"""

    def __init__(self):
        self.deleted_thread_id = None

    async def adelete_thread(self, thread_id):
        """记录删除的 Thread ID。

        Args:
            thread_id: Thread ID。
        """
        self.deleted_thread_id = thread_id


def build_client(*, actor=None, store=None, graph=None, checkpointer=None):
    """构建 Thread API 测试客户端。

    Args:
        actor: 可选当前鉴权主体。
        store: 可选测试 Run/Thread 存储。
        graph: 可选测试图。
        checkpointer: 可选测试检查点存储。
    """
    app = FastAPI()
    app.include_router(agui_router)
    app.state.agent_registry = AgentRegistry.discover()
    app.dependency_overrides[get_agui_run_store] = lambda: store or FakeThreadStore()
    app.dependency_overrides[get_agent_runtime_cache] = lambda: FakeRuntimeRegistry(
        graph or FakeGraph()
    )
    app.dependency_overrides[get_checkpointer] = lambda: checkpointer or FakeCheckpointer()
    app.dependency_overrides[get_current_actor] = lambda: actor or CurrentActor(
        is_guest=True,
        user_id=None,
        email=None,
        role="guest",
    )
    return TestClient(app)


def test_thread_list_returns_current_user_threads():
    """验证查询当前用户的 Thread 列表。"""
    client = build_client()

    response = client.get("/api/agui/threads")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["threadId"] == "thread-1"
    assert response.json()["items"][0]["agentId"] == "agent"


def test_thread_list_does_not_build_agent_graph():
    """验证 Thread 列表不会触发 Agent 图初始化。"""

    class FailRuntimeRegistry:
        """在调用时失败的运行时注册表。"""

        async def get_graph(self, request, agent, checkpointer, store):
            """在依赖被调用时抛出断言错误。

            Args:
                request: 当前请求。
                agent: 智能体类。
                checkpointer: 检查点存储。
                store: 长期存储。
            """
            raise AssertionError("Thread 列表不应构建 Agent 图")

    app = FastAPI()
    app.include_router(agui_router)
    app.dependency_overrides[get_agui_run_store] = lambda: FakeThreadStore()
    app.dependency_overrides[get_agent_runtime_cache] = FailRuntimeRegistry
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        is_guest=True,
        user_id=None,
        email=None,
        role="guest",
    )

    with TestClient(app) as client:
        response = client.get("/api/agui/threads")

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_thread_run_list_returns_snapshots():
    """验证按 Thread 查询 Run。"""
    client = build_client()

    response = client.get("/api/agui/threads/thread-1/runs")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["runId"] == "run-1"
    assert response.json()["items"][0]["agentId"] == "agent"


def test_thread_state_returns_graph_values():
    """验证读取 Thread state。"""
    client = build_client()

    response = client.get("/api/agui/threads/thread-1/state")

    assert response.status_code == 200
    assert response.json()["title"] == "测试标题"
    assert response.json()["message_created_at"] == {
        "m1": "2026-09-22T00:00:01+00:00",
        "m2": "2026-09-22T00:00:02+00:00",
    }


def test_collect_message_created_at_from_checkpoint_history():
    """验证逐条消息时间可以从 LangGraph checkpoint 历史推导出来。"""

    async def scenario():
        model = GenericFakeChatModel(
            messages=iter(
                [AIMessage(content="第一次回答"), AIMessage(content="第二次回答")]
            )
        )
        graph = create_agent(model=model, checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "thread-1"}}

        await graph.ainvoke(
            {"messages": [HumanMessage(content="第一次提问", id="m1")]},
            config,
        )
        await graph.ainvoke(
            {"messages": [HumanMessage(content="第二次提问", id="m2")]},
            config,
        )

        snapshot = await graph.aget_state(config)
        messages = snapshot.values["messages"]
        created_at = await _collect_message_created_at(graph, config)

        # 每条消息都要有时间，且时间随消息顺序单调不减。
        assert set(created_at) == {message.id for message in messages}
        ordered = [created_at[message.id] for message in messages]
        assert ordered == sorted(ordered)
        # 第一条用户消息来自第一次调用，必须早于最后一次回答。
        assert created_at["m1"] < created_at[messages[-1].id]

    asyncio.run(scenario())


def test_collect_message_created_at_returns_empty_for_empty_thread():
    """验证空 Thread 不会返回任何消息时间。"""

    async def scenario():
        graph = create_agent(
            model=GenericFakeChatModel(messages=iter([])),
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "thread-empty"}}

        assert await _collect_message_created_at(graph, config) == {}

    asyncio.run(scenario())


def test_thread_delete_removes_checkpoint_and_run_records():
    """验证删除 Thread 同时清理 checkpoint 和 Run 记录。"""
    checkpointer = FakeCheckpointer()
    client = build_client(checkpointer=checkpointer)

    response = client.delete("/api/agui/threads/thread-1")

    assert response.status_code == 200
    assert response.json() == {"threadId": "thread-1", "deleted": True}
    assert checkpointer.deleted_thread_id == "thread-1"


def test_thread_routes_are_isolated_by_actor():
    """验证其他用户不能读取或删除 Thread。"""
    actor = CurrentActor(
        is_guest=False,
        user_id="user-2",
        email="user-2@example.com",
        role="user",
    )
    client = build_client(actor=actor)

    assert client.get("/api/agui/threads/thread-1/runs").status_code == 404
    assert client.get("/api/agui/threads/thread-1/state").status_code == 404
    assert client.delete("/api/agui/threads/thread-1").status_code == 404


def test_memory_thread_store_owner_isolation():
    """验证内存 Thread 存储按 owner 隔离并支持删除。"""

    async def scenario():
        store = InMemoryRunStore()
        assert await store.create_thread(
            ThreadState(
                thread_id="thread-1",
                owner_user_id="user-1",
                agent_id="agent",
            )
        )
        assert await store.get_thread("thread-1", user_id="user-1") is not None
        assert await store.get_thread("thread-1", user_id="user-2") is None
        assert await store.delete_thread("thread-1", user_id="user-1")
        assert await store.get_thread("thread-1") is None

    asyncio.run(scenario())


def test_sql_thread_store_deletes_runs_and_events(tmp_path):
    """验证 SQL 存储删除 Thread 时同步清理 Run 与事件。"""

    async def scenario():
        """执行 SQL 存储删除场景。"""
        store = SqlRunStore(f"sqlite:///{tmp_path / 'run-store.db'}")
        await store.initialize()
        payload = RunAgentInput.model_validate(
            {
                "threadId": "thread-sql",
                "runId": "run-sql",
                "state": {"user_id": "user-1"},
                "messages": [
                    {"id": "message-sql", "role": "user", "content": "删除测试"}
                ],
                "tools": [],
            }
        )
        assert await store.create_thread(
            ThreadState(
                thread_id="thread-sql",
                owner_user_id="user-1",
                agent_id="agent",
            )
        )
        assert await store.create_run(
            RunState(
                run_id="run-sql",
                thread_id="thread-sql",
                input=payload,
                owner_user_id="user-1",
                agent_id="agent",
            )
        )
        await store.append_event("run-sql", 'data: {"type": "RUN_STARTED"}\n\n')

        assert await store.delete_thread("thread-sql", user_id="user-1")
        assert await store.get_thread("thread-sql") is None
        assert await store.get_run("run-sql") is None
        assert await store.get_events("run-sql") == []
        await store.close()

    asyncio.run(scenario())


def test_list_thread_runs_backfills_legacy_thread():
    """验证历史 Run 可直接回填 Thread 并按 Thread 查询。"""

    async def scenario():
        """执行历史 Thread 回填场景。"""
        store = InMemoryRunStore()
        payload = RunAgentInput.model_validate(
            {
                "threadId": "thread-legacy",
                "runId": "run-legacy",
                "state": {"user_id": "user-1"},
                "messages": [
                    {"id": "message-1", "role": "user", "content": "历史问题"}
                ],
                "tools": [],
                "context": [],
                "forwardedProps": {},
            }
        )
        assert await store.create_run(
            RunState(
                run_id="run-legacy",
                thread_id="thread-legacy",
                input=payload,
                owner_user_id="user-1",
                agent_id="rag",
            )
        )
        run = await store.get_run("run-legacy", user_id="user-1")
        assert run is not None

        manager = AgentRunManager(graph=None, store=store, agent_id="rag")
        try:
            runs = await manager.list_thread_runs(
                "thread-legacy",
                user_id="user-1",
                agent_id="rag",
            )
            assert runs is not None
            assert runs[0]["runId"] == "run-legacy"
            assert runs[0]["agentId"] == "rag"
            thread = await store.get_thread("thread-legacy", user_id="user-1")
            assert thread is not None
            assert thread.agent_id == "rag"
            assert thread.title == "历史问题"
            assert thread.created_at == run.created_at
            assert thread.updated_at == run.updated_at
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_sql_thread_survives_run_retention(tmp_path):
    """Run 和事件过期后 Thread 索引必须继续保留。"""

    async def scenario():
        store = SqlRunStore(
            f"sqlite:///{tmp_path / 'thread-retention.db'}",
            retention_seconds=60,
            thread_retention_seconds=0,
        )
        await store.initialize()
        assert await store.create_thread(
            ThreadState(
                thread_id="thread-persistent",
                owner_user_id="user-1",
                agent_id="agent",
                title="长期会话",
            )
        )

        await store.prune_expired()

        thread = await store.get_thread("thread-persistent", user_id="user-1")
        assert thread is not None
        assert thread.title == "长期会话"
        await store.close()

    asyncio.run(scenario())


def test_restore_threads_from_checkpoints(tmp_path):
    """缺失 Thread 索引时应从 checkpoint 恢复标题和归属。"""

    class FakeCheckpointer:
        """返回固定 checkpoint 状态的测试替身。"""

        async def aget_tuple(self, config):
            """返回指定 Thread 的状态快照。

            Args:
                config: LangGraph 运行配置。
            """
            assert config["configurable"]["thread_id"] == "thread-restored"
            return SimpleNamespace(
                checkpoint={
                    "ts": "2026-09-23T13:40:52.656327+00:00",
                    "channel_values": {
                        "user_id": "user-1",
                        "messages": [HumanMessage(content="恢复的历史问题")],
                    },
                }
            )

    async def scenario():
        store = SqlRunStore(
            f"sqlite:///{tmp_path / 'thread-backfill.db'}",
            thread_retention_seconds=0,
        )
        await store.initialize()
        async with store.async_session() as session:
            session.add(
                AgUiCheckpointRecord(
                    thread_id="thread-restored",
                    checkpoint_ns="",
                    checkpoint_id="checkpoint-1",
                    checkpoint={"channel_values": {"user_id": "user-1"}},
                )
            )
            await session.commit()

        restored = await restore_threads_from_checkpoints(
            store,
            FakeCheckpointer(),
            default_agent_id="agent",
        )

        assert restored == 1
        threads = await store.list_threads("user-1")
        assert len(threads) == 1
        assert threads[0].thread_id == "thread-restored"
        assert threads[0].title == "恢复的历史问题"
        assert threads[0].expires_at == 0
        await store.close()

    asyncio.run(scenario())


def test_persistent_thread_sentinel_is_database_safe():
    """永久 Thread 哨兵不能落入 PostgreSQL infinity 区间。"""
    assert PERSISTENT_THREAD_EXPIRES_AT.year == 9999
    assert PERSISTENT_THREAD_EXPIRES_AT.month == 12
    assert PERSISTENT_THREAD_EXPIRES_AT.day <= 30
