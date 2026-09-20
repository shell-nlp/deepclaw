__all__ = ["create_agent_router"]


def __getattr__(name: str):
    """按需导出 Agent 路由创建函数，避免 Run Manager 导入时形成循环依赖。

    Args:
        name: 请求的模块属性名。

    Returns:
        Agent 路由创建函数。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "create_agent_router":
        from deepclaw.web_backend.agent.router import create_agent_router

        return create_agent_router
    raise AttributeError(name)
