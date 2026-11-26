"""延迟工具搜索中间件测试：匹配逻辑、取回闭环与缓存重建。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain.tools import tool

from deepclaw.middleware.tool_search import (
    DeferredToolMiddleware,
    MAX_RESULTS,
    deferred_tool_search,
    tool_search,
)


@pytest.fixture
def deferred_catalog():
    """构造带名称与描述的延迟工具目录。

    Args:
        无。

    Returns:
        OpenAI function 形式的工具定义列表。
    """

    @tool
    def get_weather(location: str) -> str:
        """获取指定地点天气。"""

    @tool
    def web_fetch(url: str) -> str:
        """抓取网页内容并返回文本。"""

    @tool
    def send_email(to: str, body: str) -> str:
        """发送电子邮件到指定收件人。"""

    @tool
    def get_weather_backup(city: str) -> str:
        """获取天气(备用)渠道的信息。"""

    from langchain_core.utils.function_calling import convert_to_openai_function

    return [
        convert_to_openai_function(item)
        for item in [get_weather, web_fetch, send_email, get_weather_backup]
    ]


def test_select_exact_names(deferred_catalog):
    """select 形式按名称精确匹配。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    names = [item["name"] for item in deferred_tool_search(
        deferred_catalog, "select:get_weather,send_email"
    )]
    assert set(names) == {"get_weather", "send_email"}


def test_select_unknown_name_returns_empty(deferred_catalog):
    """select 未命中时返回空列表。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    assert deferred_tool_search(deferred_catalog, "select:nope") == []


def test_keyword_search_ranks_name_match_first(deferred_catalog):
    """关键词搜索时名称命中优先于描述命中。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    matched = deferred_tool_search(deferred_catalog, "email")
    assert matched[0]["name"] == "send_email"
    assert len(matched) <= MAX_RESULTS


def test_required_keyword_filters_and_ranks(deferred_catalog):
    """加号形式要求名称包含关键词，并按剩余词排序。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    matched = deferred_tool_search(deferred_catalog, "+web fetch")
    assert matched[0]["name"] == "web_fetch"
    assert all("web" in item["name"].lower() for item in matched)


def test_plus_only_query_returns_empty(deferred_catalog):
    """仅有加号时返回空列表而不是崩溃。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    assert deferred_tool_search(deferred_catalog, "+") == []


def test_invalid_regex_falls_back_to_literal(deferred_catalog):
    """非法正则回退为字面量匹配。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    matched = deferred_tool_search(deferred_catalog, "天气(备")
    assert [item["name"] for item in matched] == ["get_weather_backup"]


def test_tool_search_no_match_returns_message():
    """无命中时返回提示文本而不是空结果。

    Args:
        无。
    """
    runtime = SimpleNamespace(state={"deferred_tool": []}, tool_call_id="call-1")
    result = tool_search.func(query="anything", runtime=runtime)
    assert isinstance(result, str)
    assert "未找到匹配" in result


def test_tool_search_surfaces_tools_and_returns_json(deferred_catalog):
    """命中时以 JSON 返回定义，并把名称累计进已取回列表。

    Args:
        deferred_catalog: 延迟工具目录。
    """
    state = {"deferred_tool": deferred_catalog, "surfaced_tools": ["get_weather"]}
    runtime = SimpleNamespace(state=state, tool_call_id="call-1")
    result = tool_search.func(query="select:web_fetch", runtime=runtime)
    update = result.update
    assert update["surfaced_tools"] == ["get_weather", "web_fetch"]
    message = update["messages"][0]
    assert message.tool_call_id == "call-1"
    payload = json.loads(message.content)
    assert [item["name"] for item in payload] == ["web_fetch"]


class FakeRequest:
    """保留 override 行为的最小模型请求。"""

    def __init__(self, state, tools, system_prompt="系统提示"):
        """保存请求字段。

        Args:
            state: 图状态。
            tools: 工具列表。
            system_prompt: 系统提示词。
        """
        self.state = state
        self.tools = tools
        self.system_prompt = system_prompt

    def override(self, **changes):
        """创建新请求，不修改原共享对象。

        Args:
            changes: 本次修改字段。
        """
        return FakeRequest(
            self.state,
            changes.get("tools", self.tools),
            changes.get("system_prompt", self.system_prompt),
        )


def _make_tools():
    """创建两个用于测试的普通工具。

    Args:
        无。

    Returns:
        工具列表。
    """

    @tool
    def get_weather(location: str) -> str:
        """获取指定地点天气。"""

    @tool
    def web_fetch(url: str) -> str:
        """抓取网页内容并返回文本。"""

    return [get_weather, web_fetch]


def test_middleware_defers_all_tools_on_first_call():
    """首轮只绑定搜索工具，提示词列出全部延迟名称并回写目录。

    Args:
        无。
    """
    middleware = DeferredToolMiddleware()
    tools = _make_tools()
    seen = {}

    def handler(request):
        """记录模型实际收到的请求。

        Args:
            request: 最终请求。
        """
        seen["request"] = request
        return request

    result = middleware.wrap_model_call(FakeRequest({}, tools), handler)
    assert [item.name for item in seen["request"].tools] == ["tool_search"]
    assert "get_weather" in seen["request"].system_prompt
    assert "web_fetch" in seen["request"].system_prompt
    catalog = result.command.update["deferred_tool"]
    assert {item["name"] for item in catalog} == {"get_weather", "web_fetch"}


def test_middleware_rebinds_surfaced_tools():
    """已取回工具重新绑定，且不再出现在延迟清单中。

    Args:
        无。
    """
    middleware = DeferredToolMiddleware()
    tools = _make_tools()
    seen = {}

    def handler(request):
        """记录模型实际收到的请求。

        Args:
            request: 最终请求。
        """
        seen["request"] = request
        return request

    first = middleware.wrap_model_call(FakeRequest({}, tools), handler)
    catalog = first.command.update["deferred_tool"]
    state = {"deferred_tool": catalog, "surfaced_tools": ["get_weather"]}
    second = middleware.wrap_model_call(FakeRequest(state, tools), handler)

    assert [item.name for item in seen["request"].tools] == ["tool_search", "get_weather"]
    assert "get_weather" not in seen["request"].system_prompt
    assert "web_fetch" in seen["request"].system_prompt
    assert second.command is None


def test_middleware_rebuilds_catalog_when_toolset_changes():
    """工具集变化时重建目录缓存。

    Args:
        无。
    """
    middleware = DeferredToolMiddleware()
    tools = _make_tools()
    seen = {}

    def handler(request):
        """记录模型实际收到的请求。

        Args:
            request: 最终请求。
        """
        seen["request"] = request
        return request

    first = middleware.wrap_model_call(FakeRequest({}, tools), handler)
    catalog = first.command.update["deferred_tool"]
    state = {"deferred_tool": catalog}
    second = middleware.wrap_model_call(FakeRequest(state, tools[:1]), handler)
    rebuilt = second.command.update["deferred_tool"]
    assert {item["name"] for item in rebuilt} == {"get_weather"}


def test_middleware_drops_missing_surfaced_tools():
    """已取回工具不再存在时安全跳过。

    Args:
        无。
    """
    middleware = DeferredToolMiddleware()
    tools = _make_tools()
    seen = {}

    def handler(request):
        """记录模型实际收到的请求。

        Args:
            request: 最终请求。
        """
        seen["request"] = request
        return request

    first = middleware.wrap_model_call(FakeRequest({}, tools), handler)
    catalog = first.command.update["deferred_tool"]
    state = {"deferred_tool": catalog, "surfaced_tools": ["web_fetch"]}
    middleware.wrap_model_call(FakeRequest(state, tools[:1]), handler)
    assert [item.name for item in seen["request"].tools] == ["tool_search"]


def test_middleware_async_path_matches_sync():
    """异步包装与同步包装行为一致。

    Args:
        无。
    """
    middleware = DeferredToolMiddleware()
    tools = _make_tools()
    seen = {}

    async def handler(request):
        """记录模型实际收到的请求。

        Args:
            request: 最终请求。
        """
        seen["request"] = request
        return request

    async def run():
        """执行异步包装调用。

        Args:
            无。
        """
        return await middleware.awrap_model_call(FakeRequest({}, tools), handler)

    result = asyncio.run(run())
    assert [item.name for item in seen["request"].tools] == ["tool_search"]
    assert {item["name"] for item in result.command.update["deferred_tool"]} == {
        "get_weather",
        "web_fetch",
    }
