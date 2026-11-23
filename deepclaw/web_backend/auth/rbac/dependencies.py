import inspect
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import (
    CurrentActor,
    get_current_actor,
    require_authenticated_actor,
)
from deepclaw.web_backend.auth.rbac.enforcer import is_allowed


OwnerResolver = Callable[[CurrentActor], Awaitable[str | None] | str | None]


def require_permission(
    path: str,
    action: str,
    *,
    owner: OwnerResolver | None = None,
    detail: str = "没有访问权限。",
    allow_guest: bool = False,
) -> Callable[..., Awaitable[CurrentActor]]:
    """构造按 Casbin 策略校验权限的 FastAPI 依赖。

    Args:
        path: 资源路径，按策略规则匹配。
        action: 动作名称，例如 read 或 write。
        owner: 可选资源归属解析函数，返回资源所属用户 ID。
        detail: 拒绝时的错误提示。
        allow_guest: 为真时游客直接放行，仅对登录用户做策略校验；
            用于历史上对游客开放、按归属隔离的数据接口。

    Returns:
        Callable[..., Awaitable[CurrentActor]]: 可直接用于 Depends 的依赖函数。
    """

    actor_source = get_current_actor if allow_guest else require_authenticated_actor

    async def dependency(
        actor: CurrentActor = Depends(actor_source),
    ) -> CurrentActor:
        """校验当前主体是否具备目标资源权限。

        Args:
            actor: 当前鉴权主体。

        Returns:
            CurrentActor: 通过校验的主体。

        Raises:
            HTTPException: 策略拒绝时返回 403。
        """
        if allow_guest and actor.is_guest:
            return actor
        resolved_owner: str | None = None
        if owner is not None:
            candidate = owner(actor)
            resolved_owner = await candidate if inspect.isawaitable(candidate) else candidate
        if not is_allowed(actor, path=path, action=action, owner=resolved_owner):
            raise HTTPException(status_code=403, detail=detail)
        return actor

    return dependency
