import asyncio

from langchain_core.messages import AIMessage, HumanMessage


def test_recommended_questions_emits_agui_custom_event(monkeypatch):
    """验证推荐问题通过标准 custom event 发送给 AG-UI。

    Args:
        monkeypatch: pytest 提供的依赖替换工具。
    """
    import deepclaw.middleware.recommended_questions as module

    captured = {}

    class FakeRecommendModel:
        """记录结构化调用并返回固定推荐问题。"""

        def with_structured_output(self, **_kwargs):
            """返回当前替身。

            Args:
                **_kwargs: 结构化输出配置。
            """
            return self

        def bind(self, **_kwargs):
            """返回当前替身。

            Args:
                **_kwargs: 模型绑定配置。
            """
            return self

        async def ainvoke(self, _messages, **kwargs):
            """返回固定推荐问题。

            Args:
                _messages: 推荐模型输入消息。
                **kwargs: 模型调用配置。
            """
            captured["invoke_config"] = kwargs.get("config")
            return {"questions": ["问题1", "问题2", "问题3", "问题4", "问题5"]}

    async def fake_dispatch(name, data, *, config):
        """记录 AG-UI custom event。

        Args:
            name: 事件名称。
            data: 事件载荷。
            config: 事件配置。
        """
        captured["event_name"] = name
        captured["event_data"] = data
        captured["event_config"] = config

    monkeypatch.setattr(module, "get_chat_model", lambda: FakeRecommendModel())
    monkeypatch.setattr(module, "adispatch_custom_event", fake_dispatch)
    monkeypatch.setattr(module, "get_config", lambda: {"configurable": {"thread_id": "thread-1"}})

    middleware = module.RecommendedQuestionsMiddleware()
    state = {
        "messages": [
            HumanMessage(content="用户问题"),
            AIMessage(content="助手回答"),
        ]
    }
    asyncio.run(middleware.aafter_agent(state, None))

    assert captured["invoke_config"] == {
        "metadata": {"emit-messages": False, "emit-tool-calls": False}
    }
    assert captured["event_name"] == "recommended_questions"
    assert captured["event_data"]["recommended_questions"] == ["问题1", "问题2", "问题3"]
