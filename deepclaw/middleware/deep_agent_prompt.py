import sys
from typing import cast

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from deepclaw.utils import get_current_time

_platform = sys.platform
if _platform.startswith("win"):
    DEFAULT_OS_PROMPT = "你的运行环境是 Windows 系统, 你可以使用 Windows 相关的命令"
elif _platform.startswith("linux"):
    DEFAULT_OS_PROMPT = "你的运行环境是 Linux 系统, 你可以使用 Linux 相关的命令"
elif _platform.startswith("darwin"):
    DEFAULT_OS_PROMPT = "你的运行环境是 macOS 系统, 你可以使用 macOS 相关的命令"
else:
    DEFAULT_OS_PROMPT = f"你的运行环境未知: {_platform}"

DEFAULT_SYSTEM_PROMPT = f"""## 操作系统
{DEFAULT_OS_PROMPT}

## 额外要遵守的要求
- 若工具被拒绝执行，即使你可以推理出用户问题的答案，也要拒绝。
"""


class DeepAgentPromptMiddleware(AgentMiddleware):
    """在模型调用前追加通用 Agent 提示词与当前时间。"""

    def _override_system_message(self, request):
        current_time = get_current_time()
        prompt_suffix = DEFAULT_SYSTEM_PROMPT + f"\n## 系统时间{current_time}"
        if request.system_message is not None:
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": f"\n\n{prompt_suffix}"},
            ]
        else:
            new_system_content = [{"type": "text", "text": prompt_suffix}]
        new_system_message = SystemMessage(content=cast("list[str | dict[str, str]]", new_system_content))
        return request.override(system_message=new_system_message)

    def wrap_model_call(self, request, handler):
        return handler(self._override_system_message(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._override_system_message(request))
