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


def test_cron_tool_supports_add_list_remove(tmp_path):
    from deepclaw.middleware.cron.cron_manager import get_cron_manager
    from deepclaw.middleware.cron.cron_tool import cron_tool

    get_cron_manager(f"sqlite:///{tmp_path / 'cron-tool.db'}")

    added = asyncio.run(cron_tool.ainvoke(
        {
            "action": "add",
            "name": "cleanup",
            "cron_expression": "*/15 * * * *",
            "command": "python scripts/cleanup.py",
        }
    ))
    listed = asyncio.run(cron_tool.ainvoke({"action": "list"}))
    removed = asyncio.run(cron_tool.ainvoke({"action": "remove", "name": "cleanup"}))

    assert "added successfully" in added
    assert "cleanup" in listed
    assert "Cron job removed successfully" == removed


def test_cron_tool_requires_identifier_for_remove():
    from deepclaw.middleware.cron.cron_tool import cron_tool

    result = asyncio.run(cron_tool.ainvoke({"action": "remove"}))

    assert result == "Error: Please provide either job_id or name"


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

    async def handler(updated_request):
        return updated_request

    updated_request = asyncio.run(middleware.awrap_model_call(request, handler))

    assert [tool.name for tool in updated_request.tools] == [cron_tool.name]


def test_general_agent_registers_cron_middleware(monkeypatch):
    import deepclaw.agents.general.agent as agent_module
    from deepclaw.middleware.cron.middleware import CronMiddleware

    class DummyModel:
        tags = []

    captured = {}

    def fake_create_agent(**kwargs):
        captured["middleware"] = kwargs["middleware"]
        return object()

    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)
    monkeypatch.setattr(agent_module, "get_chat_model", lambda: DummyModel())
    monkeypatch.setattr(agent_module.settings, "USE_COPILOTKIT", False)
    monkeypatch.setattr(agent_module.settings, "USE_TOOL_SEARCH", False)
    monkeypatch.setattr(agent_module.settings, "BACKEND_TYPE", "")

    agent_module.Agent(deep_agent=False)

    assert any(
        isinstance(middleware, CronMiddleware)
        for middleware in captured["middleware"]
    )
