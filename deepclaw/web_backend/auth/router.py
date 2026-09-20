from fastapi import APIRouter, Depends, Header

from deepclaw.web_backend.auth.dependencies import (
    CurrentActor,
    get_current_actor,
    require_admin_actor,
    require_authenticated_actor,
)
from deepclaw.web_backend.auth.schemas import (
    AdminCreateUserRequest,
    AdminListUsersRequest,
    AdminResetUserPasswordRequest,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
    LoginRequest,
    RegisterRequest,
)
from deepclaw.web_backend.auth.service import AuthService, get_auth_service


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", summary="注册用户", description="创建普通用户账号并返回访问令牌和用户信息。")
async def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
):
    """注册普通用户并返回登录令牌。"""
    user = await service.register(email=request.email, password=request.password)
    issued = await service.login(email=request.email, password=request.password)
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
async def login(
    request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    """校验登录凭据并返回访问令牌。"""
    issued = await service.login(email=request.email, password=request.password)
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
    actor: CurrentActor = Depends(require_authenticated_actor),
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
):
    """撤销当前访问令牌。"""
    token = (authorization or "").split(" ", 1)[1]
    await service.revoke_token(token)
    return {"ok": True}


@router.get("/me", summary="获取当前用户", description="返回当前访问令牌对应的用户信息和角色权限。")
async def me(actor: CurrentActor = Depends(get_current_actor)):
    """返回当前鉴权主体。"""
    return actor.model_dump()


@router.post("/users/create", summary="创建用户", description="管理员创建指定角色和初始状态的用户账号。")
async def create_user(
    request: AdminCreateUserRequest,
    actor: CurrentActor = Depends(require_admin_actor),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员创建用户。"""
    user = await service.create_user_as_admin(
        email=request.email,
        password=request.password,
        role=request.role,
    )
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
    actor: CurrentActor = Depends(require_admin_actor),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员查询用户列表。"""
    users = await service.list_users(search=request.search)
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
    actor: CurrentActor = Depends(require_admin_actor),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员更新用户角色。"""
    user = await service.update_user_role(
        user_id=request.user_id,
        role=request.role,
    )
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
    actor: CurrentActor = Depends(require_admin_actor),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员更新用户启用状态。"""
    user = await service.update_user_status(
        user_id=request.user_id,
        is_active=request.is_active,
    )
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
    actor: CurrentActor = Depends(require_admin_actor),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员重置用户密码。"""
    user = await service.reset_user_password(
        user_id=request.user_id,
        password=request.password,
    )
    return {
        "user": {
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
        }
    }


def create_auth_router() -> APIRouter:
    """返回模块级认证路由器。"""
    return router
