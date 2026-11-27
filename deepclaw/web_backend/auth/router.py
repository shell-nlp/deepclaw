from fastapi import APIRouter, Depends, Header

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import (
    CurrentActor,
    get_current_actor,
    require_authenticated_actor,
)
from deepclaw.web_backend.auth.rbac import get_enforcer, require_permission
from deepclaw.web_backend.auth.schemas import (
    AdminCreateUserRequest,
    AdminDeleteUserRequest,
    AdminListUsersRequest,
    AdminUpdateUserProfileRequest,
    AdminResetUserPasswordRequest,
    AdminUpdateUserRoleRequest,
    AdminUpdateUserStatusRequest,
    LoginRequest,
    RegisterRequest,
)
from deepclaw.web_backend.auth.service import AuthService, get_auth_service


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config", summary="获取认证配置", description="返回公开的登录策略开关，供前端决定游客入口与注册入口是否展示。")
async def auth_config():
    """返回登录策略开关。"""
    return {
        "allow_guest": settings.ALLOW_GUEST_ACCESS,
        "allow_registration": settings.AUTH_ALLOW_REGISTRATION,
    }


@router.post("/register", summary="注册用户", description="创建普通用户账号并返回访问令牌和用户信息。")
async def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
):
    """注册普通用户并返回登录令牌。"""
    user = await service.register(
        username=request.username,
        password=request.password,
        email=request.email,
    )
    issued = await service.login(username=request.username, password=request.password)
    return {
        "token": issued.token,
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        },
    }


@router.post("/login", summary="用户登录", description="校验用户名和密码，成功后返回访问令牌和用户信息。")
async def login(
    request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    """校验登录凭据并返回访问令牌。"""
    issued = await service.login(username=request.username, password=request.password)
    return {
        "token": issued.token,
        "user": {
            "username": issued.user.username,
            "display_name": issued.user.display_name,
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
    """返回当前鉴权主体及其实际 RBAC 权限。

    Args:
        actor: 当前鉴权主体。

    Returns:
        dict: 用户资料与权限路径动作列表。
    """
    permissions: list[dict[str, str]] = []
    if not actor.is_guest:
        try:
            permissions = [
                {"path": rule[1], "action": rule[2]}
                for rule in get_enforcer().get_implicit_permissions_for_user(actor.role)
                if len(rule) >= 3
            ]
        except Exception:
            permissions = []
    response = actor.model_dump()
    response["permissions"] = permissions
    return response


@router.post("/users/create", summary="创建用户", description="管理员创建指定角色和初始状态的用户账号。")
async def create_user(
    request: AdminCreateUserRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/create", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员创建用户。"""
    user = await service.create_user_as_admin(
        username=request.username,
        password=request.password,
        role=request.role,
        email=request.email,
        display_name=request.display_name,
    )
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    }


@router.post("/users/list", summary="查询用户列表", description="管理员分页查询系统用户及其角色、状态信息。")
async def list_users(
    request: AdminListUsersRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/list", "read")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员查询用户列表。"""
    users = await service.list_users(search=request.search)
    return {
        "items": [
            {
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            }
            for user in users
        ],
        "total": len(users),
    }


@router.post("/users/update-role", summary="修改用户角色", description="管理员更新指定用户的角色。")
async def update_user_role(
    request: AdminUpdateUserRoleRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/update-role", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员更新用户角色。"""
    user = await service.update_user_role(
        user_id=request.user_id,
        role=request.role,
    )
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    }


@router.post("/users/update-status", summary="修改用户状态", description="管理员启用或禁用指定用户。")
async def update_user_status(
    request: AdminUpdateUserStatusRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/update-status", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员更新用户启用状态。"""
    user = await service.update_user_status(
        user_id=request.user_id,
        is_active=request.is_active,
    )
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    }


@router.post("/users/update", summary="修改用户资料", description="管理员修改指定用户的用户名、显示名与邮箱。")
async def update_user_profile(
    request: AdminUpdateUserProfileRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/update", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员修改账号资料。"""
    user = await service.update_user_profile(
        user_id=request.user_id,
        username=request.username,
        email=request.email,
        display_name=request.display_name,
    )
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    }


@router.post("/users/delete", summary="删除用户", description="管理员删除指定用户，禁止删除自己或最后一个管理员。")
async def delete_user(
    request: AdminDeleteUserRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/delete", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员删除用户账号。"""
    deleted = await service.delete_user(
        user_id=request.user_id,
        operator_user_id=actor.user_id,
    )
    return {"deleted": deleted}


@router.post("/users/reset-password", summary="重置用户密码", description="管理员为指定用户设置新的登录密码。")
async def reset_user_password(
    request: AdminResetUserPasswordRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/users/reset-password", "write")),
    service: AuthService = Depends(get_auth_service),
):
    """由管理员重置用户密码。"""
    user = await service.reset_user_password(
        user_id=request.user_id,
        password=request.password,
    )
    return {
        "user": {
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "user_id": user.user_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    }
