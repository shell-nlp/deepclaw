import asyncio
from pathlib import Path


def build_manager(db_path: Path):
    from deepclaw.middleware.cron.cron_manager import CronManager

    return CronManager(f"sqlite:///{db_path}")


def test_cron_manager_add_list_remove_roundtrip(tmp_path):
    manager = build_manager(tmp_path / "cron.db")

    created = asyncio.run(manager.add(
        name="daily-report",
        cron_expression="0 9 * * *",
        command="python scripts/report.py",
        description="日报任务",
    ))
    listed = asyncio.run(manager.list())
    removed = asyncio.run(manager.remove(job_id=created.id))

    assert created.id is not None
    assert [job.name for job in listed] == ["daily-report"]
    assert removed is True
    assert asyncio.run(manager.list()) == []


def test_cron_tool_supports_crud_and_account_isolation(tmp_path, monkeypatch):
    """通过 ToolRuntime 校验聊天工具的增删改查和账号隔离。

    Args:
        tmp_path: 隔离的数据库目录。
        monkeypatch: 测试替换工具。
    """
    import importlib
    import json
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from deepclaw.middleware.cron.cron_tool import cron_tool
    from deepclaw.middleware.cron.schedule_store import ScheduleStore
    from deepclaw.web_backend.agent.run_manager import AgentAuthUser

    store = ScheduleStore(f"sqlite:///{tmp_path / 'test.db'}")
    tool_module = importlib.import_module("deepclaw.middleware.cron.cron_tool")
    monkeypatch.setattr(tool_module, "get_schedule_store", lambda: store)

    async def agent_has_permission(user_id, path, action):
        """模拟一个仅允许查看任务的角色。

        Args:
            user_id: 当前账号。
            path: 授权功能路径。
            action: 授权动作。
        """
        return path == "/api/schedules" and (user_id != "viewer" or action == "read")

    monkeypatch.setattr(tool_module, "agent_has_permission", agent_has_permission)
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([cron_tool]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()

    async def invoke(user, action, **args):
        """在实际工具节点中模拟已经认证的聊天。

        Args:
            user: 用户 ID。
            action: 工具动作。
            args: 动作参数。
        """
        message = AIMessage(content="", tool_calls=[
            {"name": "cron_tool", "args": {"action": action, **args}, "id": action}
        ])
        result = await compiled.ainvoke(
            {"messages": [message]},
            {"configurable": {"langgraph_auth_user": AgentAuthUser(identity=user)}},
        )
        return result["messages"][-1].content

    async def run():
        """验证任务工具的完整交互。

        Args:
            无。
        """
        assert "请登录" in await invoke("guest", "list")
        assert json.loads(await invoke("viewer", "list")) == []
        assert "没有访问" in await invoke("viewer", "add")
        created = json.loads(await invoke("owner", "add", changes={
            "name": "日报", "content": "准备日报", "cron": "0 9 * * 1-5",
        }))
        assert json.loads(await invoke("other", "list")) == []
        assert json.loads(await invoke("owner", "list"))[0]["id"] == created["id"]
        edited = json.loads(await invoke("owner", "update", job_id=created["id"], changes={"enabled": False}))
        assert edited["next_at"] is None
        assert "找不到" in await invoke("other", "remove", job_id=created["id"])
        assert "已删除" in await invoke("owner", "remove", job_id=created["id"])
        await store.engine.dispose()

    asyncio.run(run())

class DummyRequest:
    def __init__(self, tools):
        self.tools = tools

    def override(self, **kwargs):
        return DummyRequest(kwargs["tools"])


def test_cron_middleware_appends_cron_tool():
    from deepclaw.middleware.cron.cron_tool import cron_tool
    from deepclaw.middleware.cron.middleware import CronMiddleware

    middleware = CronMiddleware()
    request = DummyRequest(tools=[])

    def handler(updated_request):
        return updated_request

    updated_request = middleware.wrap_model_call(request, handler)

    assert [tool.name for tool in updated_request.tools] == [cron_tool.name]


def test_cron_middleware_does_not_duplicate_existing_tool():
    """验证 cron 工具已存在时不会被重复追加。"""
    from deepclaw.middleware.cron.cron_tool import cron_tool
    from deepclaw.middleware.cron.middleware import CronMiddleware

    middleware = CronMiddleware()
    request = DummyRequest(tools=[cron_tool])

    def handler(updated_request):
        return updated_request

    updated_request = middleware.wrap_model_call(request, handler)

    assert [tool.name for tool in updated_request.tools] == [cron_tool.name]


def test_general_agent_registers_cron_middleware(monkeypatch):
    """验证通用 Agent 注册 CronMiddleware。"""
    from deepclaw.middleware.cron.middleware import CronMiddleware

    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured["middleware"] = kwargs["middleware"]
        return object()

    monkeypatch.setattr(
        "deepagents.create_deep_agent",
        fake_create_deep_agent,
    )
    import deepclaw.agents.general.agent as agent_module

    class DummyModel:
        tags = []

    monkeypatch.setattr(agent_module, "get_chat_model", lambda: DummyModel())
    monkeypatch.setattr(agent_module.settings, "USE_COPILOTKIT", False)
    monkeypatch.setattr(agent_module.settings, "USE_TOOL_SEARCH", False)
    monkeypatch.setattr(agent_module.settings, "BACKEND_TYPE", "local_shell")

    agent_module.GeneralAgent.build_agent(deep_agent=True)

    assert any(
        isinstance(m, CronMiddleware)
        for m in captured["middleware"]
    )


def test_general_agent_uses_exact_token_counter_for_summarization(monkeypatch):
    from deepclaw.utils import count_message_tokens

    captured = {}

    class DummySummarizationMiddleware:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    def fake_create_agent(**kwargs):
        captured["middleware"] = kwargs["middleware"]
        return object()

    import langchain.agents.middleware as middleware_module
    import deepclaw.agents.general.agent as agent_module

    class DummyModel:
        tags = []

    monkeypatch.setattr(middleware_module, "SummarizationMiddleware", DummySummarizationMiddleware)
    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    monkeypatch.setattr(agent_module, "get_chat_model", lambda: DummyModel())
    monkeypatch.setattr(agent_module.settings, "USE_COPILOTKIT", False)
    monkeypatch.setattr(agent_module.settings, "USE_TOOL_SEARCH", False)
    monkeypatch.setattr(agent_module.settings, "BACKEND_TYPE", "local_shell")

    agent_module.GeneralAgent.build_agent(deep_agent=False)

    assert captured["kwargs"]["token_counter"] is count_message_tokens
    assert captured["kwargs"]["trigger"] == ("fraction", 0.8)
