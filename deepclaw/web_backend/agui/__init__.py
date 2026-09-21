"""AG-UI 统一路由与智能体注册表。"""

__all__ = ["router"]


def __getattr__(name: str):
    """按需导出统一 AG-UI 路由器。

    Args:
        name: 请求的模块属性名。

    Returns:
        统一 AG-UI 路由器。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "router":
        from deepclaw.web_backend.agui.router import router

        return router
    raise AttributeError(name)
