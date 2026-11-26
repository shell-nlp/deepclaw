"""延迟工具搜索中间件：先只暴露工具名称，模型按需检索后恢复工具可调用。"""

import json
import re
from typing import Any, NotRequired

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ExtendedModelResponse
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_function
from langgraph.types import Command
from loguru import logger

MAX_RESULTS = 3


def _compile_query(pattern: str) -> re.Pattern:
    """编译查询正则，非法表达式回退为字面量匹配。

    Args:
        pattern: 查询表达式。

    Returns:
        大小写不敏感的已编译正则。
    """
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def _searchable_text(tool_def: dict) -> str:
    """拼接工具的可搜索文本。

    Args:
        tool_def: OpenAI function 形式的工具定义。

    Returns:
        名称与描述拼接的文本。
    """
    description = tool_def.get("description") or ""
    return f"{tool_def['name']} {description}"


def deferred_tool_search(deferred_tool: list[dict], query: str) -> list[dict]:
    """按正则表达式模式搜索延迟工具，匹配名称和描述。支持三种查询形式（与 Claude Code 保持一致）：
    "select:name1,name2" — 精确匹配名称
    "+keyword rest" — 名称必须包含关键词，按 rest 排序
    "keyword query" — 对名称和描述进行正则表达式匹配
    Args:
        deferred_tool: 延迟工具的 OpenAI function 定义列表。
        query: 检索查询。

    Returns:
        匹配的工具定义列表，最多 MAX_RESULTS 条。
    """
    if query.startswith("select:"):
        names = {n.strip() for n in query[7:].split(",") if n.strip()}
        return [tool for tool in deferred_tool if tool["name"] in names][:MAX_RESULTS]

    if query.startswith("+"):
        parts = query[1:].split(None, 1)
        if not parts:
            return []
        required = parts[0].lower()
        candidates = [
            tool for tool in deferred_tool if required in tool["name"].lower()
        ]
        if len(parts) > 1:
            regex = _compile_query(parts[1])
            candidates.sort(
                key=lambda tool: len(regex.findall(_searchable_text(tool))),
                reverse=True,
            )
        return candidates[:MAX_RESULTS]

    regex = _compile_query(query)
    scored: list[tuple[int, dict]] = []
    for tool_def in deferred_tool:
        if regex.search(_searchable_text(tool_def)):
            score = 2 if regex.search(tool_def["name"]) else 1
            scored.append((score, tool_def))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [tool_def for _, tool_def in scored][:MAX_RESULTS]


class ToolSearchState(AgentState):
    """延迟工具搜索的状态扩展。

    Args:
        无。
    """

    deferred_tool: NotRequired[list[dict]]
    surfaced_tools: NotRequired[list[str]]


@tool
def tool_search(query: str, runtime: ToolRuntime) -> str | Command:
    """获取延迟工具完整架构定义，使其可被调用。
    延迟工具会在系统提示词的 <available-deferred-tools> 中显示名称。在获取之前，仅知道其名称——没有参数架构，因此无法调用该工具。此工具接收查询，将其与延迟工具列表进行匹配，并返回匹配工具的完整定义。取回的工具会在后续对话中恢复绑定，即可直接调用。
    查询形式：
    "select:Read,Edit,Grep" —— fetch these exact tools by name
    "notebook jupyter" —— keyword search, up to max_results best matches
    "+slack send" —— require "slack" in the name, rank by remaining terms
    参数：
    query: 用于查找延迟工具的查询。使用 "select:<tool_name>" 进行直接选择，或使用关键词进行搜索。
    返回：
    匹配的工具定义，以 JSON 数组形式返回。
    """
    deferred_tool = runtime.state.get("deferred_tool") or []
    matched_tools = deferred_tool_search(deferred_tool, query)
    if not matched_tools:
        return f"未找到匹配的工具: {query}"

    # 取回即恢复：记录名称，让后续模型调用把这些工具重新绑定。
    surfaced = list(runtime.state.get("surfaced_tools") or [])
    surfaced.extend(
        item["name"] for item in matched_tools if item["name"] not in surfaced
    )
    tool_defs_json = json.dumps(matched_tools, ensure_ascii=False)
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=tool_defs_json, tool_call_id=runtime.tool_call_id
                )
            ],
            "surfaced_tools": surfaced,
        }
    )


class DeferredToolMiddleware(AgentMiddleware):
    """延迟工具中间件：隐藏工具架构只暴露名称，模型检索后恢复绑定。

    Args:
        无。
    """

    tools = [tool_search]
    state_schema = ToolSearchState

    def _prepare_request(self, request: Any) -> tuple[Any, Command | None]:
        """计算提示词与工具列表调整后的请求，以及延迟目录的状态更新。

        Args:
            request: 当前模型请求。

        Returns:
            (调整后的请求, 需要写入延迟工具目录的 Command，目录未变化时为 None)。
        """
        state = request.state or {}
        current_tools = [
            item
            for item in request.tools
            if isinstance(item, BaseTool) and item.name != tool_search.name
        ]
        tool_by_name = {item.name: item for item in current_tools}
        current_names = set(tool_by_name)

        cached_catalog = state.get("deferred_tool") or []
        cached_names = {item["name"] for item in cached_catalog}
        command: Command | None = None
        if current_names != cached_names:
            # 工具集变化（首轮、MCP 配置更新等）时重建目录，避免清单与缓存脱节。
            cached_catalog = [
                convert_to_openai_function(item) for item in current_tools
            ]
            logger.info(f"刷新 {len(cached_catalog)} 个延迟工具到状态")
            command = Command(update={"deferred_tool": cached_catalog})

        surfaced_names = [
            name for name in (state.get("surfaced_tools") or [])
            if name in tool_by_name
        ]
        surfaced_set = set(surfaced_names)

        deferred_names = [
            item.name for item in current_tools if item.name not in surfaced_set
        ]
        deferred_tool_prompt = (
            "\n<available-deferred-tools>\n"
            + "\n".join(deferred_names)
            + "\n</available-deferred-tools>\n"
        )
        new_system_prompt = request.system_prompt + deferred_tool_prompt
        new_request = request.override(
            system_prompt=new_system_prompt,
            tools=[tool_search, *(tool_by_name[name] for name in surfaced_names)],
        )
        return new_request, command

    def wrap_model_call(self, request, handler):
        """同步包装模型调用，只绑定搜索工具与已取回工具。

        Args:
            request: 当前模型请求。
            handler: 后续模型调用。

        Returns:
            模型响应，必要时附带延迟目录状态更新。
        """
        new_request, command = self._prepare_request(request)
        return ExtendedModelResponse(
            model_response=handler(new_request),
            command=command,
        )

    async def awrap_model_call(self, request, handler):
        """异步包装模型调用，只绑定搜索工具与已取回工具。

        Args:
            request: 当前模型请求。
            handler: 后续模型调用。

        Returns:
            模型响应，必要时附带延迟目录状态更新。
        """
        new_request, command = self._prepare_request(request)
        return ExtendedModelResponse(
            model_response=await handler(new_request),
            command=command,
        )
