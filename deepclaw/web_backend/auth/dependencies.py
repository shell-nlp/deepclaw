from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

from deepclaw.web_backend.auth.service import AuthService, get_auth_service


class CurrentActor(BaseModel):
    is_guest: bool
    user_id: str | None
    email: str | None
    role: str


async def get_current_actor(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> CurrentActor:
    if not authorization:
        return CurrentActor(is_guest=True, user_id=None, email=None, role="guest")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")

    try:
        actor = await service.authenticate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return CurrentActor(
        is_guest=False,
        user_id=actor.user.user_id,
        email=actor.user.email,
        role=actor.user.role,
    )


def require_authenticated_actor(
    actor: CurrentActor = Depends(get_current_actor),
) -> CurrentActor:
    if actor.is_guest:
        raise HTTPException(status_code=403, detail="请先登录后再使用该功能。")
    return actor


def require_admin_actor(
    actor: CurrentActor = Depends(require_authenticated_actor),
) -> CurrentActor:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以执行该操作。")
    return actor

