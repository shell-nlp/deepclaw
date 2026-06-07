from fastapi import APIRouter, Depends, Header, HTTPException

from langchain_api.api.auth.schemas.auth import LoginRequest, RegisterRequest
from langchain_api.api.auth.schemas.users import (
    AdminCreateUserRequest,
    AdminListUsersRequest,
    AdminResetUserPasswordRequest,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
)
from langchain_api.auth.dependencies import CurrentActor
from langchain_api.auth.service import AuthService, get_auth_service


def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def create_auth_router(service: AuthService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    auth_service = service or get_auth_service()

    def current_actor_from_service(
        authorization: str | None = Header(default=None),
    ) -> CurrentActor:
        if not authorization:
            return CurrentActor(is_guest=True, user_id=None, email=None, role="guest")

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")

        try:
            actor = auth_service.authenticate_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        return CurrentActor(
            is_guest=False,
            user_id=actor.user.user_id,
            email=actor.user.email,
            role=actor.user.role,
        )

    def authenticated_actor_from_service(
        actor: CurrentActor = Depends(current_actor_from_service),
    ) -> CurrentActor:
        if actor.is_guest:
            raise HTTPException(status_code=403, detail="请先登录后再使用该功能。")
        return actor

    def admin_actor_from_service(
        actor: CurrentActor = Depends(authenticated_actor_from_service),
    ) -> CurrentActor:
        if actor.role != "admin":
            raise HTTPException(status_code=403, detail="只有管理员可以执行该操作。")
        return actor

    @router.post("/register")
    def register(request: RegisterRequest):
        try:
            user = auth_service.register(email=request.email, password=request.password)
            issued = auth_service.login(email=request.email, password=request.password)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "token": issued.token,
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            },
        }

    @router.post("/login")
    def login(request: LoginRequest):
        try:
            issued = auth_service.login(email=request.email, password=request.password)
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "token": issued.token,
            "user": {
                "email": issued.user.email,
                "role": issued.user.role,
                "is_active": issued.user.is_active,
                "user_id": issued.user.user_id,
            },
        }

    @router.post("/logout")
    def logout(
        actor=Depends(authenticated_actor_from_service),
        authorization: str | None = Header(default=None),
    ):
        token = (authorization or "").split(" ", 1)[1]
        auth_service.revoke_token(token)
        return {"ok": True}

    @router.get("/me")
    def me(actor=Depends(current_actor_from_service)):
        return actor.model_dump()

    @router.post("/users/create")
    def create_user(
        request: AdminCreateUserRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = auth_service.create_user_as_admin(
                email=request.email,
                password=request.password,
                role=request.role,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            }
        }

    @router.post("/users/list")
    def list_users(
        request: AdminListUsersRequest,
        actor=Depends(admin_actor_from_service),
    ):
        users = auth_service.list_users(search=request.search)
        return {
            "items": [
                {
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "user_id": user.user_id,
                }
                for user in users
            ],
            "total": len(users),
        }

    @router.post("/users/update-role")
    def update_user_role(
        request: AdminUpdateUserRoleRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = auth_service.update_user_role(
                user_id=request.user_id,
                role=request.role,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            }
        }

    @router.post("/users/update-status")
    def update_user_status(
        request: AdminUpdateUserStatusRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = auth_service.update_user_status(
                user_id=request.user_id,
                is_active=request.is_active,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            }
        }

    @router.post("/users/reset-password")
    def reset_user_password(
        request: AdminResetUserPasswordRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = auth_service.reset_user_password(
                user_id=request.user_id,
                password=request.password,
            )
        except ValueError as exc:
            raise _handle_value_error(exc) from exc

        return {
            "user": {
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            }
        }

    return router
