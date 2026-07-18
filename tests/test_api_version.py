from deepclaw.web_backend.common.api_version import (
    get_agent_general_api_path,
    get_channel_agent_api_url,
    get_rag_general_api_path,
    get_runtime_api_config,
)


def test_general_api_paths_for_v1_and_v2():
    assert get_agent_general_api_path("v1") == "/api/agent/general_api"
    assert get_agent_general_api_path("v2") == "/api/agent/v2/general_api"
    assert get_rag_general_api_path("v1") == "/api/rag/general_api"
    assert get_rag_general_api_path("v2") == "/api/rag/v2/general_api"


def test_channel_agent_api_url_prefers_explicit_override():
    url = get_channel_agent_api_url(
        explicit_url="http://example.com/custom",
        version="v2",
    )
    assert url == "http://example.com/custom"


def test_channel_agent_api_url_uses_version_when_no_override():
    url = get_channel_agent_api_url(
        explicit_url=None,
        host="127.0.0.1",
        port=7869,
        version="v2",
    )
    assert url == "http://127.0.0.1:7869/api/agent/v2/general_api"


def test_runtime_api_config_keys():
    config = get_runtime_api_config()
    assert "general_api_version" in config
    assert "agent_general_api_path" in config
    assert "rag_general_api_path" in config
