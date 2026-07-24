from typing import List, TypedDict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from loguru import logger

from deepclaw.utils import get_chat_model


class RecommendQuestions(TypedDict):
    """推荐问题的结构化输出模式。"""
    questions: List[str]


class RecommendedQuestionsMiddleware(AgentMiddleware):
    """推荐问题中间件。"""

    async def aafter_agent(self, state, runtime):
        messages = state.get("messages", [])
        stream_writer = runtime.stream_writer
        user_input = next(
            (msg.content for msg in reversed(messages) if isinstance(msg, HumanMessage)),
            None,
        )

        recommend_model = (
            get_chat_model()
            .with_structured_output(
                schema=RecommendQuestions,
                method="json_mode",
            )
            .bind(extra_body={"thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}})
        )
        recommend_result = await recommend_model.ainvoke(
            [
                (
                    "system",
                    """请根据用户当前问题生成 3 个与当前问题相关的新问题。
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
""",
                ),
                (
                    "human",
                    f"当前问题：{user_input}",
                ),
            ]
        )
        recommended_questions = recommend_result.get("questions") or []
        recommended_questions = list(set(recommended_questions))[:3]
        logger.info(f"推荐问题：{recommended_questions}")
        stream_writer({"recommended_questions": recommended_questions})
