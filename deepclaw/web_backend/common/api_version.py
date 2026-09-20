"""AG-UI 运行时路径解析。

浏览器与渠道统一使用 Run 生命周期接口；旧 general_api 版本开关仅保留给历史配置，
不再参与新运行路径选择。
"""

from typing import Literal

from deepclaw.settings import settings

GeneralApiVersion = Literal["v1", "v2"]


def get_agent_runs_path() -> str:
    """返回 Agent AG-UI Runs 路径。

    Returns:
        固定为 ``/api/agent/runs``。
    """
    return "/api/agent/runs"


def get_rag_runs_path() -> str:
    """返回 RAG AG-UI Runs 路径。

    Returns:
        固定为 ``/api/rag/runs``。
    """
    return "/api/rag/runs"


def get_agent_general_api_path(version: GeneralApiVersion | None = None) -> str:
    """兼容旧调用，返回 Agent AG-UI Runs 路径。

    Args:
        version: 已废弃的旧版本参数。

    Returns:
        Agent Runs 路径。
    """
    _ = version
    return get_agent_runs_path()


def get_rag_general_api_path(version: GeneralApiVersion | None = None) -> str:
    """兼容旧调用，返回 RAG AG-UI Runs 路径。

    Args:
        version: 已废弃的旧版本参数。

    Returns:
        RAG Runs 路径。
    """
    _ = version
    return get_rag_runs_path()


def get_channel_agent_api_url(
    *,
    explicit_url: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
    version: GeneralApiVersion | None = None,
) -> str:
    """解析渠道调用的 Agent Runs 完整 URL。

    Args:
        explicit_url: 可选完整覆盖 URL；非空时直接使用。
        host: 自动拼接时使用的主机名。
        port: 自动拼接时使用的端口；为空时取 settings.PORT。
        version: 已废弃的旧版本参数。

    Returns:
        渠道可调用的 Agent Runs URL。
    """
    _ = version
    if explicit_url:
        return explicit_url
    resolved_port = settings.PORT if port is None else port
    return f"http://{host}:{resolved_port}{get_agent_runs_path()}"


def get_runtime_api_config() -> dict[str, str]:
    """构造前端 runtime-config 响应体。

    Returns:
        包含 Agent/RAG Runs 路径的配置字典。
    """
    return {
        "agent_runs_path": get_agent_runs_path(),
        "rag_runs_path": get_rag_runs_path(),
    }
