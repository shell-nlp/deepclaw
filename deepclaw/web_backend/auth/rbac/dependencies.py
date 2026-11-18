import inspect
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor, require_authenticated_actor
from deepclaw.web_backend.auth.rbac.enforcer import is_allowed


OwnerResolver = Callable[[CurrentActor], Awaitable[str | None] | str | None]


def require_permission(
    path: str,
    action: str,
    *,
    owner: OwnerResolver | None = None,
    detail: str = "没有访问权限。",
) -> Callable[..., Awaitable[CurrentActor]]:
    """构造按 Casbin 策略校验权限的 FastAPI 依赖。

    Args:
        path: 资源路径，按策略规则匹配。
        action: 动作名称，例如 read 或 write。
        owner: 可选资源归属解析函数，返回资源所属用户 ID。
        detail: 拒绝时的错误提示。

    Returns:
        Callable[..., Awaitable[CurrentActor]]: 可直接用于 Depends 的依赖函数。
    """

    async def dependency(
        actor: CurrentActor = Depends(require_authenticated_actor),
    ) -> CurrentActor:
        """校验当前主体是否具备目标资源权限。

        Args:
            actor: 当前鉴权主体。

        Returns:
            CurrentActor: 通过校验的主体。

        Raises:
            HTTPException: 策略拒绝时返回 403。
        """
        resolved_owner: str | None = None
        if owner is not None:
            candidate = owner(actor)
            resolved_owner = await candidate if inspect.isawaitable(candidate) else candidate
        if not is_allowed(actor, path=path, action=action, owner=resolved_owner):
            raise HTTPException(status_code=403, detail=detail)
        return actor

    return dependency
