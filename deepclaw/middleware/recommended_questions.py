from typing import List, TypedDict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from deepclaw.utils import get_chat_model


class RecommendedQuestionsMiddleware(AgentMiddleware):
    """推荐问题中间件"""

    async def aafter_agent(self, state, runtime):
        messages = state.get("messages", [])
        stream_writer = runtime.stream_writer
        conversation_turns = []
        current_turn = None
        for msg in messages:
            if isinstance(msg, HumanMessage):
                current_turn = {"question": msg.content, "answers": []}
                conversation_turns.append(current_turn)
            elif isinstance(msg, AIMessage) and current_turn is not None and msg.content:
                current_turn["answers"].append(msg.content)

        recent_conversation = conversation_turns[-6:]
        conversation_context = "\n\n".join(
            f"第{index}轮\n用户问题：{turn['question']}\n助手回答：{'\n'.join(turn['answers'])}"
            for index, turn in enumerate(recent_conversation, start=1)
        )

        class RecommendQuestions(TypedDict):
            questions: List[str]

        recommend_model = (
            get_chat_model()
            .with_structured_output(
                schema=RecommendQuestions,
                method="json_mode",
            )
            .bind(
                extra_body={
                    "thinking": {"type": "disabled"},
                    "chat_template_kwargs": {"enable_thinking": False},
                    "response_format": {"type": "json_object"},
                }
            )
        )
        recommend_result = await recommend_model.ainvoke(
            [
                (
                    "system",
                    """请根据最近 6 轮用户问题和助手回答生成 5 个与上下文相关的新问题。
## 要求
- 必须输出结构化 JSON，对应字段为 questions,形如：
{
  "questions": [
    "问题1",
    "问题2",
    "问题3"
  ]
}

- questions 必须恰好包含 5 个问题
- 每个问题都必须是完整通顺的中文问句，并以中文问号结尾，且要简短。
- 不要重复用户原问题
- 生成的问题不能是重复的
- 生成的问题必须与最近对话上下文相关，避免脱离当前任务。
""",
                ),
                (
                    "human",
                    f"最近 6 轮对话：\n{conversation_context}",
                ),
            ]
        )
        recommended_questions = recommend_result.get("questions") or []
        recommended_questions = list(set(recommended_questions))[:3]
        logger.info(f"推荐问题：{recommended_questions}")
        stream_writer({"recommended_questions": recommended_questions})
