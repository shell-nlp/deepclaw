import asyncio

from langchain.agents.middleware import AgentMiddleware
from loguru import logger

from deepclaw.backend.open_sandbox import OpenSandbox

open_sandbox = OpenSandbox()


class OpenSandboxKillMiddleware(AgentMiddleware):
    """Open沙箱杀死中间件"""

    def after_agent(self, state, runtime):
        """目的：在代理执行完成后，统一杀死用户的沙箱环境"""

        user_id = runtime.context.user_id
        user_store_item = runtime.store.get((f"user_{user_id}",), "sandbox_id")
        if user_store_item:
            try:
                sandbox = open_sandbox.connect_sandbox(user_store_item.value["sandbox_id"])
                sandbox.kill()
            except Exception as e:
                logger.warning(f"杀死沙箱 {user_store_item.value['sandbox_id']} 失败({e})，清理 store 记录")
            runtime.store.delete((f"user_{user_id}",), "sandbox_id")
            logger.debug(f"用户: {user_id} 的沙箱已被杀死, ID 为 {user_store_item.value['sandbox_id']} ")

    async def aafter_agent(self, state, runtime):
        return await asyncio.to_thread(self.after_agent, state, runtime)
