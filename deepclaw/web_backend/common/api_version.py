"""通用 API 版本解析。

通过 settings.GENERAL_API_VERSION 统一控制前端与渠道默认走 v1 还是 v2。
"""

from typing import Literal

from deepclaw.settings import settings

GeneralApiVersion = Literal["v1", "v2"]


def get_general_api_version() -> GeneralApiVersion:
    """读取当前通用 API 版本配置。

    Returns:
        当前版本：``v1`` 或 ``v2``。
    """
    version = settings.GENERAL_API_VERSION
    if version not in ("v1", "v2"):
        return "v1"
    return version


def get_agent_general_api_path(version: GeneralApiVersion | None = None) -> str:
    """解析 Agent general_api 路径。

    Args:
        version: 指定版本；为空时读取全局配置。
    """
    resolved = version or get_general_api_version()
    if resolved == "v2":
        return "/api/agent/v2/general_api"
    return "/api/agent/general_api"


def get_rag_general_api_path(version: GeneralApiVersion | None = None) -> str:
    """解析 RAG general_api 路径。

    Args:
        version: 指定版本；为空时读取全局配置。
    """
    resolved = version or get_general_api_version()
    if resolved == "v2":
        return "/api/rag/v2/general_api"
    return "/api/rag/general_api"


def get_channel_agent_api_url(
    *,
    explicit_url: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    version: GeneralApiVersion | None = None,
) -> str:
    """解析渠道调用的 Agent general_api 完整 URL。

    Args:
        explicit_url: 可选完整覆盖 URL；非空时直接使用。
        host: 自动拼接时使用的主机名。
        port: 自动拼接时使用的端口；为空时取 settings.PORT。
        version: 指定版本；为空时读取全局配置。
    """
    if explicit_url:
        return explicit_url
    resolved_port = settings.PORT if port is None else port
    path = get_agent_general_api_path(version)
    return f"http://{host}:{resolved_port}{path}"


def get_runtime_api_config() -> dict[str, str]:
    """构造前端 runtime-config 响应体。

    Returns:
        包含版本与路径的配置字典。
    """
    version = get_general_api_version()
    return {
        "general_api_version": version,
        "agent_general_api_path": get_agent_general_api_path(version),
        "rag_general_api_path": get_rag_general_api_path(version),
    }
