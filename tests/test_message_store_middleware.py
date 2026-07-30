import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from deepclaw.middleware.message_store import (
    MessageStoreMiddleware,
    ThreadMessageStore,
)


def test_message_store_middleware_saves_messages_before_model_call(monkeypatch, tmp_path):
    """验证同一线程在模型调用前即保存消息，且后续覆盖更新。"""
    from deepclaw.middleware import message_store

    async def run_test():
        store = ThreadMessageStore(f"sqlite:///{tmp_path / 'thread_messages.db'}")
        middleware = MessageStoreMiddleware(message_store=store)
        runtime = Runtime()
        monkeypatch.setattr(
            message_store,
            "get_config",
            lambda: {"configurable": {"thread_id": "thread-1"}},
        )

        await middleware.abefore_agent(
            {"messages": [HumanMessage(content="第一次提问")]},
            runtime,
        )
        before_finish = await store.get_messages("thread-1")
        await middleware.abefore_model(
            {"messages": [HumanMessage(content="第一次提问")]},
            runtime,
        )
        duplicate_save = await store.get_messages("thread-1")
        await middleware.abefore_model(
            {
                "messages": [
                    HumanMessage(content="第一次提问"),
                    AIMessage(content="第一次回答"),
                ]
            },
            runtime,
        )

        record = await store.get_messages("thread-1")
        await store.close()

        assert before_finish is not None
        assert before_finish.messages[0]["data"]["content"] == "第一次提问"
        assert duplicate_save is not None
        assert duplicate_save.updated_at == before_finish.updated_at
        assert record is not None
        assert record.messages[-1]["data"]["content"] == "第一次回答"

    asyncio.run(run_test())
