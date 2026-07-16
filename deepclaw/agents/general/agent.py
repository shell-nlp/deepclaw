from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from loguru import logger

from deepclaw.agents.general.context import AgentContext
from deepclaw.constant import (
    AGENT_VIRTUAL_PREFERENCES,
    SANDBOX_SHARED_AGENTS,
    SANDBOX_SHARED_SKILLS,
    SANDBOX_USER_AGENTS,
    SANDBOX_USER_SKILLS,
    home_path,
    workspace_path,
)
from deepclaw.middleware.common import BusinessMiddleware
from deepclaw.middleware.mcp import MCPMiddleware
from deepclaw.settings import settings
from deepclaw.utils import get_chat_model


def user_namespace_factory(runtime: Runtime[Any]) -> tuple[str, ...]:
    """动态生成用户namespace：('user123', 'filesystem')"""
    user_id = runtime.context.user_id  # 从context获取
    # TODO 获取config,未来可实现共享命名空间
    # from langchain_core.runnables.config import var_child_runnable_config
    # config = var_child_runnable_config.get()
    return ("filesystem", user_id)  # 用户隔离！


class Agent:
    def __init__(
        self,
        system_prompt="",
        tools: list = [],
        deep_agent: bool = False,
        checkpointer=None,
        store=None,
    ):
        self.system_prompt = system_prompt
        self.tools = tools
        self.checkpointer = checkpointer
        self.store = store
        self.deep_agent = deep_agent
        self.agent = self.init_agent()

    def get_common_middleware(self):
        """获取通用中间件列表"""
        middleware = []
        if settings.USE_COPILOTKIT:
            from copilotkit import CopilotKitMiddleware

            middleware.append(CopilotKitMiddleware())

        middleware.append(BusinessMiddleware())
        middleware.append(MCPMiddleware())
        return middleware

    def get_common_tools(self):
        """获取通用工具列表"""
        from deepclaw.tools import get_weather, web_fetch

        return [get_weather, web_fetch]

    def init_agent(self) -> CompiledStateGraph:
        skills = None
        memory = None
        middleware = self.get_common_middleware()

        model = get_chat_model()
        model.tags = ["agent"]

        backend = None
        tools = self.tools + self.get_common_tools()

        if not workspace_path.exists():
            workspace_path.mkdir(parents=True, exist_ok=True)
        if settings.BACKEND_TYPE == "sandbox":
            from deepclaw.backend.open_sandbox import OpenSandbox
            from deepclaw.middleware.sandbox.opensandbox_kill import OpenSandboxKillMiddleware

            # 注意：以下是 Docker 容器内路径（容器 OS 永远为 Linux），
            # 与宿主 OS 无关，不要替换为 workspace_path 等 host 路径。
            skills = [SANDBOX_SHARED_SKILLS, SANDBOX_USER_SKILLS]
            memory = [SANDBOX_SHARED_AGENTS, SANDBOX_USER_AGENTS]
            middleware.append(OpenSandboxKillMiddleware())
            backend = OpenSandbox()
            logger.info("使用 OpenSandbox 作为后端")
        elif settings.BACKEND_TYPE == "local_shell":
            from deepagents.backends.local_shell import LocalShellBackend

            # 宿主机路径，使用 pathlib.Path 自动处理 Windows / Linux / macOS 分隔符
            skills = [str(workspace_path / "skills")]
            memory = [str(workspace_path / "AGENTS.md")]
            backend = LocalShellBackend(root_dir=home_path, virtual_mode=False, inherit_env=True)
            logger.info("使用 LocalShellBackend 作为后端")
        elif settings.BACKEND_TYPE == "store":
            from deepclaw.agents.general.utils import copy_skills_to_store

            copy_skills_to_store(skills_dir=workspace_path / "skills", store=self.store)
            logger.info("使用 StoreBackend 作为后端")

        def make_backend(runtime):
            from deepagents.backends import CompositeBackend, StoreBackend

            nonlocal backend
            if settings.BACKEND_TYPE == "store":
                backend = StoreBackend(namespace=user_namespace_factory)

            return CompositeBackend(
                default=backend,
                routes={
                    "/memories/": StoreBackend(namespace=user_namespace_factory),
                },
            )

        if settings.USE_TOOL_SEARCH:
            from deepclaw.middleware.tool_search import DeferredToolMiddleware

            middleware.append(DeferredToolMiddleware())
        # HumanInTheLoopMiddleware
        # middleware.append(
        #     HumanInTheLoopMiddleware(
        #         interrupt_on={
        #             "execute": {
        #                 "allowed_decisions": ["approve", "edit", "reject"],
        #                 "description": "工具执行等待批准",
        #             },
        #         },
        #         description_prefix="工具执行等待批准",
        #     )
        # )

        if self.deep_agent:
            from deepclaw.middleware.chart import ChartMiddleware
            from deepclaw.middleware.cron.middleware import CronMiddleware
            from deepclaw.middleware.deep_agent_prompt import DeepAgentPromptMiddleware

            middleware.append(ChartMiddleware())
            middleware.append(DeepAgentPromptMiddleware())
            middleware.append(CronMiddleware())
            logger.info("使用 DeepAgent")
            from deepagents import FilesystemPermission, create_deep_agent

            memory.append(AGENT_VIRTUAL_PREFERENCES)
            return create_deep_agent(
                model=model,
                tools=tools,
                system_prompt=self.system_prompt,
                middleware=middleware,
                backend=make_backend,
                skills=skills,
                memory=memory,
                checkpointer=self.checkpointer,
                store=self.store,
                context_schema=AgentContext,
                permissions=[FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="allow")],
            )
        else:
            logger.info("正在使用 ReactAgent")
            from langchain.agents import create_agent
            from langchain.agents.middleware import SummarizationMiddleware

            middleware.append(SummarizationMiddleware(model=get_chat_model()))
            return create_agent(
                model=model,
                tools=tools,
                system_prompt=self.system_prompt,
                middleware=middleware,
                checkpointer=self.checkpointer,
                store=self.store,
                context_schema=AgentContext,
            )

    def get_agent(self) -> CompiledStateGraph:
        return self.agent


if __name__ == "__main__":
    model = get_chat_model()
    for chunk in model.stream("1+1="):
        print(chunk)
