__all__ = ["router"]


def __getattr__(name: str):
    """按需导出 Agent 路由器，避免导入阶段构造运行时对象。

    Args:
        name: 请求的模块属性名。

    Returns:
        Agent 路由器。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "router":
        from deepclaw.web_backend.agent.router import router

        return router
    raise AttributeError(name)
