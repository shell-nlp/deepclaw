from fastapi import APIRouter, Depends, Header, HTTPException

from deepclaw.web_backend.auth.schemas import (
    AdminCreateUserRequest,
    AdminListUsersRequest,
    AdminResetUserPasswordRequest,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
    LoginRequest,
    RegisterRequest,
)
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.service import AuthService, get_auth_service


def _handle_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def create_auth_router(service: AuthService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    auth_service = service or get_auth_service()

    async def current_actor_from_service(
        authorization: str | None = Header(default=None),
    ) -> CurrentActor:
        if not authorization:
            return CurrentActor(is_guest=True, user_id=None, email=None, role="guest")

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")

        try:
            actor = await auth_service.authenticate_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        return CurrentActor(
            is_guest=False,
            user_id=actor.user.user_id,
            email=actor.user.email,
            role=actor.user.role,
        )

    async def authenticated_actor_from_service(
        actor: CurrentActor = Depends(current_actor_from_service),
    ) -> CurrentActor:
        if actor.is_guest:
            raise HTTPException(status_code=403, detail="请先登录后再使用该功能。")
        return actor

    async def admin_actor_from_service(
        actor: CurrentActor = Depends(authenticated_actor_from_service),
    ) -> CurrentActor:
        if actor.role != "admin":
            raise HTTPException(status_code=403, detail="只有管理员可以执行该操作。")
        return actor

    @router.post("/register", summary="注册用户", description="创建普通用户账号并返回访问令牌和用户信息。")
    async def register(request: RegisterRequest):
        try:
            user = await auth_service.register(email=request.email, password=request.password)
            issued = await auth_service.login(email=request.email, password=request.password)
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

    @router.post("/login", summary="用户登录", description="校验邮箱和密码，成功后返回访问令牌和用户信息。")
    async def login(request: LoginRequest):
        try:
            issued = await auth_service.login(email=request.email, password=request.password)
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

    @router.post("/logout", summary="用户退出", description="撤销当前请求使用的访问令牌。")
    async def logout(
        actor=Depends(authenticated_actor_from_service),
        authorization: str | None = Header(default=None),
    ):
        token = (authorization or "").split(" ", 1)[1]
        await auth_service.revoke_token(token)
        return {"ok": True}

    @router.get("/me", summary="获取当前用户", description="返回当前访问令牌对应的用户信息和角色权限。")
    async def me(actor=Depends(current_actor_from_service)):
        return actor.model_dump()

    @router.post("/users/create", summary="创建用户", description="管理员创建指定角色和初始状态的用户账号。")
    async def create_user(
        request: AdminCreateUserRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = await auth_service.create_user_as_admin(
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

    @router.post("/users/list", summary="查询用户列表", description="管理员分页查询系统用户及其角色、状态信息。")
    async def list_users(
        request: AdminListUsersRequest,
        actor=Depends(admin_actor_from_service),
    ):
        users = await auth_service.list_users(search=request.search)
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

    @router.post("/users/update-role", summary="修改用户角色", description="管理员更新指定用户的角色。")
    async def update_user_role(
        request: AdminUpdateUserRoleRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = await auth_service.update_user_role(
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

    @router.post("/users/update-status", summary="修改用户状态", description="管理员启用或禁用指定用户。")
    async def update_user_status(
        request: AdminUpdateUserStatusRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = await auth_service.update_user_status(
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

    @router.post("/users/reset-password", summary="重置用户密码", description="管理员为指定用户设置新的登录密码。")
    async def reset_user_password(
        request: AdminResetUserPasswordRequest,
        actor=Depends(admin_actor_from_service),
    ):
        try:
            user = await auth_service.reset_user_password(
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

