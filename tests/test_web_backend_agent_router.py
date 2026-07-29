from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deepclaw.web_backend.agent import router as agent_router


class FakeAgent:
    """用于隔离路由测试的 Agent 替身。"""

    def __init__(self, *args, **kwargs):
        """创建不初始化真实模型的测试替身。

        Args:
        - args: 位置参数。
        - kwargs: 关键字参数。
        """

    def get_agent(self):
        """返回路由注册所需的占位 Agent。"""
        return object()


class FakeLangGraphAgent:
    """避免测试时初始化真实 AG-UI 图适配器。"""

    def __init__(self, *args, **kwargs):
        """接收 AG-UI 适配器的构造参数。

        Args:
        - args: 位置参数。
        - kwargs: 关键字参数。
        """


class FakeStateGraph:
    """提供固定聊天状态的测试图。"""

    async def aget_state(self, config):
        """返回带首条消息的测试状态。

        Args:
        - config: 图状态查询配置。
        """
        assert config == {"configurable": {"thread_id": "session-state"}}
        return SimpleNamespace(
            values={"messages": [SimpleNamespace(content="会话标题")]}
        )


class FakeStateAgent:
    """用于测试会话状态接口的 Agent 替身。"""

    def __init__(self, *args, **kwargs):
        """接收路由创建 Agent 时传入的参数。

        Args:
        - args: 位置参数。
        - kwargs: 关键字参数。
        """

    def get_agent(self):
        """返回提供固定状态的测试图。"""
        return FakeStateGraph()


class FakeCheckpointer:
    """提供固定检查点的测试检查点存储。"""

    async def alist(self, config):
        """按最近检查点优先的顺序返回测试数据。

        Args:
        - config: 检查点查询配置。
        """
        assert config is None
        yield SimpleNamespace(
            config={"configurable": {"thread_id": "session-new"}}
        )
        yield SimpleNamespace(
            config={"configurable": {"thread_id": "session-old"}}
        )
        yield SimpleNamespace(
            config={"configurable": {"thread_id": "session-new"}}
        )

    async def adelete_thread(self, session_id):
        """记录待删除的会话 ID。

        Args:
        - session_id: 待删除的会话 ID。
        """
        self.deleted_session_id = session_id


class FakeAsyncPostgresSaver:
    """用于验证 PostgreSQL 会话列表查询分支的检查点存储替身。"""


class FailingCheckpointer:
    """模拟删除会话时发生故障的检查点存储。"""

    async def adelete_thread(self, session_id):
        """抛出删除检查点失败异常。

        Args:
        - session_id: 待删除的会话 ID。
        """
        raise RuntimeError("database unavailable")


def noop_endpoint(*args, **kwargs):
    """跳过与会话列表无关的流式路由注册。

    Args:
    - args: 位置参数。
    - kwargs: 关键字参数。
    """


def test_list_sessions_returns_deduplicated_session_ids(monkeypatch):
    """会话列表接口应按检查点顺序返回去重后的 session_id。"""
    monkeypatch.setattr(agent_router, "Agent", FakeAgent)
    monkeypatch.setattr(agent_router, "LangGraphAgent", FakeLangGraphAgent)
    monkeypatch.setattr(
        agent_router,
        "add_langgraph_fastapi_endpoint",
        noop_endpoint,
    )
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v1", noop_endpoint)
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v2", noop_endpoint)

    app = FastAPI()
    app.include_router(agent_router.create_agent_router(FakeCheckpointer()))

    with TestClient(app) as client:
        response = client.get("/api/agent/get_session_list")

    assert response.status_code == 200
    assert response.json() == {
        "code": "200",
        "msg": "查询成功",
        "data": {
            "session_ids": ["session-new", "session-old"],
            "total": 2,
        },
    }


def test_list_sessions_queries_postgres_thread_ids_directly(monkeypatch):
    """PostgreSQL 会话列表接口应直接查询 checkpoints 的 thread_id。"""
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(
        return_value=[{"thread_id": "session-new"}, {"thread_id": "session-old"}]
    )
    cursor_context = MagicMock()
    cursor_context.__aenter__ = AsyncMock(return_value=cursor)
    cursor_context.__aexit__ = AsyncMock(return_value=False)
    connection = MagicMock()
    connection.cursor.return_value = cursor_context
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=False)
    checkpointer = FakeAsyncPostgresSaver()
    checkpointer.conn = MagicMock()
    checkpointer.conn.connection.return_value = connection_context

    monkeypatch.setattr(agent_router, "Agent", FakeAgent)
    monkeypatch.setattr(agent_router, "LangGraphAgent", FakeLangGraphAgent)
    monkeypatch.setattr(agent_router, "AsyncPostgresSaver", FakeAsyncPostgresSaver)
    monkeypatch.setattr(
        agent_router,
        "add_langgraph_fastapi_endpoint",
        noop_endpoint,
    )
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v1", noop_endpoint)
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v2", noop_endpoint)

    app = FastAPI()
    app.include_router(agent_router.create_agent_router(checkpointer))

    with TestClient(app) as client:
        response = client.get("/api/agent/get_session_list")

    assert response.status_code == 200
    assert response.json() == {
        "code": "200",
        "msg": "查询成功",
        "data": {
            "session_ids": ["session-new", "session-old"],
            "total": 2,
        },
    }
    assert "GROUP BY thread_id" in cursor.execute.await_args.args[0]


def test_delete_session_calls_checkpointer_delete_thread(monkeypatch):
    """删除会话接口应调用检查点存储的异步删除方法。"""
    checkpointer = FakeCheckpointer()
    monkeypatch.setattr(agent_router, "Agent", FakeAgent)
    monkeypatch.setattr(agent_router, "LangGraphAgent", FakeLangGraphAgent)
    monkeypatch.setattr(
        agent_router,
        "add_langgraph_fastapi_endpoint",
        noop_endpoint,
    )
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v1", noop_endpoint)
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v2", noop_endpoint)

    app = FastAPI()
    app.include_router(agent_router.create_agent_router(checkpointer))

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/delete_session",
            json={"session_id": "session-to-delete"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "200",
        "msg": "删除成功",
        "data": {"session_id": "session-to-delete"},
    }
    assert checkpointer.deleted_session_id == "session-to-delete"


def test_delete_session_returns_error_when_checkpointer_fails(monkeypatch):
    """检查点删除失败时接口应返回明确的服务端错误。"""
    monkeypatch.setattr(agent_router, "Agent", FakeAgent)
    monkeypatch.setattr(agent_router, "LangGraphAgent", FakeLangGraphAgent)
    monkeypatch.setattr(
        agent_router,
        "add_langgraph_fastapi_endpoint",
        noop_endpoint,
    )
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v1", noop_endpoint)
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v2", noop_endpoint)

    app = FastAPI()
    app.include_router(agent_router.create_agent_router(FailingCheckpointer()))

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/delete_session",
            json={"session_id": "session-to-delete"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "code": "500",
        "msg": "删除会话失败",
        "data": None,
    }


def test_get_state_returns_standard_response(monkeypatch):
    """会话状态接口应将完整状态放入统一响应的 data 字段。"""
    monkeypatch.setattr(agent_router, "Agent", FakeStateAgent)
    monkeypatch.setattr(agent_router, "LangGraphAgent", FakeLangGraphAgent)
    monkeypatch.setattr(
        agent_router,
        "add_langgraph_fastapi_endpoint",
        noop_endpoint,
    )
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v1", noop_endpoint)
    monkeypatch.setattr(agent_router, "add_general_api_endpoint_v2", noop_endpoint)

    app = FastAPI()
    app.include_router(agent_router.create_agent_router(FakeCheckpointer()))

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/get_state",
            json={"session_id": "session-state"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "200",
        "msg": "查询成功",
        "data": {
            "messages": [{"content": "会话标题"}],
            "title": "会话标题",
        },
    }
