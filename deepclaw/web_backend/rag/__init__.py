__all__ = ["router"]


def __getattr__(name: str):
    """按需导出 RAG 路由器。

    Args:
        name: 请求的模块属性名。

    Returns:
        RAG 路由器。

    Raises:
        AttributeError: 请求的属性不存在。
    """
    if name == "router":
        from deepclaw.web_backend.rag.router import router

        return router
    raise AttributeError(name)
