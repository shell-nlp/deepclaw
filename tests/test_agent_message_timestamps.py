import asyncio

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from deepclaw.web_backend.agent.message_timestamps import (
    collect_message_created_at,
)


def test_collect_message_created_at_from_checkpoint_history():
    """验证逐条消息时间可以从 LangGraph checkpoint 历史推导出来。"""

    async def scenario():
        model = GenericFakeChatModel(
            messages=iter([AIMessage(content="第一次回答"), AIMessage(content="第二次回答")])
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
        created_at = await collect_message_created_at(graph, config)

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

        assert await collect_message_created_at(graph, config) == {}

    asyncio.run(scenario())
