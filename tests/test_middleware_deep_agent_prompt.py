import asyncio

from langchain_core.messages import SystemMessage


class DummyRequest:
    def __init__(self, system_message):
        self.system_message = system_message

    def override(self, **kwargs):
        return DummyRequest(kwargs["system_message"])


def test_deep_agent_prompt_middleware_appends_default_prompt_and_time(monkeypatch):
    from deepclaw.middleware.deep_agent_prompt import (
        DEFAULT_SYSTEM_PROMPT,
        DeepAgentPromptMiddleware,
    )

    middleware = DeepAgentPromptMiddleware()
    request = DummyRequest(system_message=SystemMessage(content="自定义前缀"))
    monkeypatch.setattr(
        "deepclaw.utils.get_current_time",
        lambda: "\n当前时间：2099年1月1日 星期一",
    )

    async def handler(updated_request):
        return updated_request

    updated_request = asyncio.run(middleware.awrap_model_call(request, handler))

    assert updated_request.system_message.content_blocks == [
        {"type": "text", "text": "自定义前缀"},
        {
            "type": "text",
            "text": f"\n\n{DEFAULT_SYSTEM_PROMPT}",
        },
    ]


def test_general_agent_registers_deep_agent_prompt_middleware(monkeypatch):
    from deepclaw.middleware.deep_agent_prompt import DeepAgentPromptMiddleware

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

    agent_module.Agent(deep_agent=True)

    assert any(
        isinstance(m, DeepAgentPromptMiddleware)
        for m in captured["middleware"]
    )
