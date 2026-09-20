from __future__ import annotations


class BusinessRuleError(ValueError):
    """业务规则校验失败异常，由全局异常处理器转换为 HTTP 响应。

    Args:
        message: 面向调用方的错误说明。
        status_code: 转换后的 HTTP 状态码。
    """

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        """初始化业务规则异常。

        Args:
            message: 面向调用方的错误说明。
            status_code: 转换后的 HTTP 状态码。

        Returns:
            无。
        """
        super().__init__(message)
        self.status_code = status_code
