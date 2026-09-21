from deepclaw.web_backend.common.agui_runs import (
    get_agui_agents_path,
    get_agui_runs_path,
    get_channel_agent_api_url,
    get_runtime_api_config,
)


def test_agui_runs_paths():
    """验证 Agent 与 RAG 统一使用 AG-UI Runs 路径。"""
    assert get_agui_runs_path() == "/api/agui/runs"
    assert get_agui_agents_path() == "/api/agui/agents"


def test_channel_agent_api_url_prefers_explicit_override():
    """验证渠道显式 URL 优先。"""
    url = get_channel_agent_api_url(
        explicit_url="http://example.com/custom",
    )
    assert url == "http://example.com/custom"


def test_channel_agent_api_url_uses_runs_path():
    """验证渠道自动拼接 Agent Runs URL。"""
    url = get_channel_agent_api_url(
        explicit_url=None,
        host="127.0.0.1",
        port=7869,
    )
    assert url == "http://127.0.0.1:7869/api/agui/runs"


def test_runtime_api_config_keys():
    """验证前端运行时配置包含 AG-UI Runs 路径。"""
    config = get_runtime_api_config()
    assert config == {
        "agui_runs_path": "/api/agui/runs",
        "agents_path": "/api/agui/agents",
    }
