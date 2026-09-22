from typing import Any

from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from deepclaw.agent_registry import Agent
from deepclaw.agents.general.state import StateSchema
from deepclaw.constant import (
    AGENT_VIRTUAL_PREFERENCES,
    HOME_PATH,
    SANDBOX_SHARED_AGENTS,
    SANDBOX_SHARED_SKILLS,
    SANDBOX_USER_AGENTS,
    SANDBOX_USER_SKILLS,
    WORKSPACE_PATH,
)
from deepclaw.settings import settings
from deepclaw.utils import get_chat_model


def user_namespace_factory(runtime: Any) -> tuple[str, ...]:
    """动态生成用户 namespace。

    Args:
        runtime: 当前 Agent 运行时，优先读取运行时身份信息。
    """
    server_info = getattr(runtime, "server_info", None)
    user = getattr(server_info, "user", None)
    identity = getattr(user, "identity", None)
    user_id = str(identity) if identity else "default"
    return ("filesystem", user_id)


class GeneralAgent(Agent):
    """通用智能体。"""

    agent_id = "agent"
    name = "通用智能体"
    description = "通用工具调用、MCP 与深度思考"
    capabilities = frozenset({"mcp", "deep_thinking", "internet_search"})
    allowed_state_keys = frozenset({"internet_search", "deep_thinking", "mcp_config"})
    is_default = True

    @classmethod
    def get_common_middleware(cls) -> list:
        """返回所有 Agent 可复用的通用中间件。

        Args:
            无。

        Returns:
            通用中间件实例列表。
        """
        from langchain.agents.middleware.human_in_the_loop import (
            HumanInTheLoopMiddleware,
        )

        from deepclaw.middleware import (
            BusinessMiddleware,
            MCPMiddleware,
            RecommendedQuestionsMiddleware,
        )
        from deepclaw.middleware.chart import ChartMiddleware

        def when_get_weather(request) -> bool:
            """判断天气工具调用是否需要人工审批。

            Args:
                request: 工具调用请求。
            """
            query = request.tool_call["args"].get("location", "")
            return query.startswith("南阳")

        return [
            RecommendedQuestionsMiddleware(),
            BusinessMiddleware(),
            MCPMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "get_weather": {
                        "allowed_decisions": ["approve", "edit", "reject"],
                        "description": "工具执行等待批准",
                        "when": when_get_weather,
                    },
                    "ask_user": True,
                },
                description_prefix="工具执行等待批准",
            ),
            ChartMiddleware(),
        ]

    @classmethod
    def get_common_tools(cls) -> list:
        """返回所有 Agent 可复用的通用工具。

        Args:
            无。

        Returns:
            通用工具列表。
        """
        from deepclaw.tools import ask_user, get_weather, web_fetch

        return [get_weather, web_fetch, ask_user]

    @classmethod
    def build_agent(
        cls,
        *,
        system_prompt: str = "",
        tools: list | None = None,
        deep_agent: bool = False,
        checkpointer: Any | None = None,
        store: Any | None = None,
    ) -> CompiledStateGraph:
        """构建通用 Agent 图。

        Args:
            system_prompt: Agent 系统提示词。
            tools: 额外工具列表。
            deep_agent: 是否构建 DeepAgent。
            checkpointer: LangGraph 检查点存储。
            store: LangGraph 长期存储。

        Returns:
            已装配的通用 Agent 图。
        """

        middleware = cls.get_common_middleware()
        agent_tools = cls.get_common_tools()

        skills = None
        memory = None
        model = get_chat_model()
        model.tags = ["agent"]

        backend = None

        if not WORKSPACE_PATH.exists():
            WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
        if settings.BACKEND_TYPE == "sandbox":
            from deepclaw.backend.open_sandbox import OpenSandbox
            from deepclaw.middleware.sandbox.opensandbox_kill import (
                OpenSandboxKillMiddleware,
            )

            # 注意：以下是 Docker 容器内路径（容器 OS 永远为 Linux），
            # 与宿主 OS 无关，不要替换为 WORKSPACE_PATH 等 host 路径。
            skills = [SANDBOX_SHARED_SKILLS, SANDBOX_USER_SKILLS]
            memory = [SANDBOX_SHARED_AGENTS, SANDBOX_USER_AGENTS]
            middleware.append(OpenSandboxKillMiddleware())
            backend = OpenSandbox()
            logger.info("使用 OpenSandbox 作为后端")
        elif settings.BACKEND_TYPE == "local_shell":
            from deepagents.backends.local_shell import LocalShellBackend

            # 宿主机路径，使用 pathlib.Path 自动处理 Windows / Linux / macOS 分隔符
            skills = [str(WORKSPACE_PATH / "skills")]
            memory = [str(WORKSPACE_PATH / "AGENTS.md")]
            backend = LocalShellBackend(
                root_dir=HOME_PATH,
                virtual_mode=False,
                inherit_env=True,
            )
            logger.info("使用 LocalShellBackend 作为后端")
        elif settings.BACKEND_TYPE == "store":
            from deepclaw.agents.general.utils import copy_skills_to_store

            copy_skills_to_store(
                skills_dir=WORKSPACE_PATH / "skills",
                store=store,
            )
            logger.info("使用 StoreBackend 作为后端")

        from deepagents.backends import CompositeBackend, StoreBackend

        if settings.BACKEND_TYPE == "store":
            backend = StoreBackend(namespace=user_namespace_factory)

        composite_backend = CompositeBackend(
            default=backend,
            routes={"/memories/": StoreBackend(namespace=user_namespace_factory)},
        )

        if settings.USE_TOOL_SEARCH:
            from deepclaw.middleware.tool_search import DeferredToolMiddleware

            middleware.append(DeferredToolMiddleware())

        if deep_agent:
            from deepclaw.middleware.deep_agent_prompt import (
                DeepAgentPromptMiddleware,
            )

            middleware.extend(
                [
                    DeepAgentPromptMiddleware(),
                ]
            )
            logger.info("使用 DeepAgent")
            from deepagents import FilesystemPermission, create_deep_agent

            permissions = None
            if settings.BACKEND_TYPE == "store":
                permissions = [
                    FilesystemPermission(
                        operations=["read", "write"],
                        paths=["/**"],
                        mode="allow",
                    )
                ]

            memory.append(AGENT_VIRTUAL_PREFERENCES)
            return create_deep_agent(
                model=model,
                tools=agent_tools,
                system_prompt=system_prompt,
                middleware=middleware,
                backend=composite_backend,
                skills=skills,
                memory=memory,
                checkpointer=checkpointer,
                store=store,
                state_schema=StateSchema,
                permissions=permissions,
            )

        logger.info("正在使用 ReactAgent")
        from langchain.agents import create_agent
        from langchain.agents.middleware import SummarizationMiddleware

        middleware.extend(
            [
                SummarizationMiddleware(
                    model=get_chat_model(),
                    # token_counter=count_message_tokens,
                ),
            ]
        )
        return create_agent(
            model=model,
            tools=agent_tools,
            system_prompt=system_prompt,
            middleware=middleware,
            checkpointer=checkpointer,
            store=store,
            state_schema=StateSchema,
        )


if __name__ == "__main__":
    model = get_chat_model()
    for chunk in model.stream("1+1="):
        print(chunk)
