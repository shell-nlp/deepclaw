import sys
from typing import Any

from deepagents import create_deep_agent
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from loguru import logger

from deepclaw.agents.general.context import AgentContext
from deepclaw.constant import home_path, workspace_path
from deepclaw.middleware.common import BusinessMiddleware
from deepclaw.middleware.mcp import MCPMiddleware
from deepclaw.settings import settings
from deepclaw.utils import get_chat_model, get_current_time

_platform = sys.platform
if _platform.startswith("win"):
    DEFUALT_OS_PROMPT = "你的运行环境是 Windows 系统, 你可以使用 Windows 相关的命令"
elif _platform.startswith("linux"):
    DEFUALT_OS_PROMPT = "你的运行环境是 Linux 系统, 你可以使用 Linux 相关的命令"
elif _platform.startswith("darwin"):
    DEFUALT_OS_PROMPT = "你的运行环境是 macOS 系统, 你可以使用 macOS 相关的命令"
else:
    DEFUALT_OS_PROMPT = f"你的运行环境未知: {_platform}"

skills = ["/workspace/skills"]


def user_namespace_factory(runtime: Runtime[Any]) -> tuple[str, ...]:
    """动态生成用户namespace：('user123', 'filesystem')"""
    user_id = runtime.context.user_id  # 从context获取
    # TODO 获取config,未来可实现共享命名空间
    # from langchain_core.runnables.config import var_child_runnable_config
    # config = var_child_runnable_config.get()
    return ("filesystem", user_id)  # 用户隔离！


DEFUALT_SYSTEM_PROMPT = f"""
{DEFUALT_OS_PROMPT}

## 额外要遵守的要求
- 若工具被拒绝执行，即使你可以推理出用户问题的答案，也要拒绝。
"""


class Agent:
    def __init__(
        self,
        system_prompt=DEFUALT_SYSTEM_PROMPT,
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

    def init_agent(self) -> CompiledStateGraph:
        middleware = []
        if settings.USE_COPILOTKIT:
            from copilotkit import CopilotKitMiddleware

            middleware.append(CopilotKitMiddleware())
        middleware.append(BusinessMiddleware())
        middleware.append(MCPMiddleware())

        system_prompt = self.system_prompt + get_current_time()
        model = get_chat_model()
        model.tags = ["agent"]
        from deepclaw.tools import get_weather, web_fetch

        backend = None
        tools = self.tools + [get_weather, web_fetch]

        if not workspace_path.exists():
            workspace_path.mkdir(parents=True, exist_ok=True)
        if settings.BACKEND_TYPE == "sandbox":
            from opensandbox.models.sandboxes import Host, Volume

            from deepclaw.backend.open_sandbox import OpenSandbox

            backend = OpenSandbox(
                volumes=[
                    Volume(
                        name="workspace-root",
                        host=Host(path=str(workspace_path)),
                        mount_path="/workspace",
                    )
                ]
            )
            logger.info("使用 OpenSandbox 作为后端")
        elif settings.BACKEND_TYPE == "local_shell":
            from deepagents.backends.local_shell import LocalShellBackend

            backend = LocalShellBackend(
                root_dir=home_path, virtual_mode=True, inherit_env=True
            )
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
            logger.info("使用 DeepAgent")

            return create_deep_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                middleware=middleware,
                backend=make_backend,
                skills=skills,
                checkpointer=self.checkpointer,
                store=self.store,
                context_schema=AgentContext,
            )
        else:
            logger.info("正在使用 ReactAgent")

            return create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
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
