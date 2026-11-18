from fastapi import APIRouter, Depends, HTTPException

from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import reload_enforcer, require_permission
from deepclaw.web_backend.auth.rbac.schemas import (
    RbacPolicyCreateRequest,
    RbacPolicyDeleteRequest,
    RbacPolicyItemResponse,
    RbacPolicyListResponse,
    RbacRoleCreateRequest,
    RbacRoleDeleteRequest,
    RbacRoleItemResponse,
)
from deepclaw.web_backend.auth.rbac.store import RbacPolicyStore, get_rbac_policy_store


router = APIRouter(prefix="/api/auth/rbac", tags=["rbac"])


async def _build_snapshot(store: RbacPolicyStore) -> RbacPolicyListResponse:
    """读取当前策略与角色快照。

    Args:
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 完整策略视图。
    """
    policies = await store.list_policies()
    roles = await store.list_roles()
    return RbacPolicyListResponse(
        policies=[
            RbacPolicyItemResponse(subject=rule.subject, path=rule.path, action=rule.action)
            for rule in policies
        ],
        roles=[RbacRoleItemResponse(child=rule.child, parent=rule.parent) for rule in roles],
    )


@router.get(
    "/policies",
    response_model=RbacPolicyListResponse,
    summary="查询 RBAC 策略",
    description="管理员查看当前全部策略与角色继承关系。",
)
async def list_rbac_policies(
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/policies", "read")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacPolicyListResponse:
    """返回策略与角色的完整视图。

    Args:
        actor: 当前鉴权主体。
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 完整策略视图。
    """
    return await _build_snapshot(store)


@router.post(
    "/policies",
    response_model=RbacPolicyListResponse,
    summary="新增 RBAC 策略",
    description="管理员新增一条策略并立即生效。",
)
async def create_rbac_policy(
    request: RbacPolicyCreateRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/policies/create", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacPolicyListResponse:
    """新增策略并重载授权引擎。

    Args:
        request: 新增策略参数。
        actor: 当前鉴权主体。
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 更新后的完整策略视图。
    """
    await store.add_policy(request.subject, request.path, request.action)
    reload_enforcer()
    return await _build_snapshot(store)


@router.post(
    "/policies/delete",
    response_model=RbacPolicyListResponse,
    summary="删除 RBAC 策略",
    description="管理员删除一条策略并立即生效。",
)
async def delete_rbac_policy(
    request: RbacPolicyDeleteRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/policies/delete", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacPolicyListResponse:
    """删除策略并重载授权引擎。

    Args:
        request: 删除策略参数。
        actor: 当前鉴权主体。
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 更新后的完整策略视图。

    Raises:
        HTTPException: 策略不存在时返回 404。
    """
    deleted = await store.delete_policy(request.subject, request.path, request.action)
    if not deleted:
        raise HTTPException(status_code=404, detail="策略不存在。")
    reload_enforcer()
    return await _build_snapshot(store)


@router.post(
    "/roles",
    response_model=RbacPolicyListResponse,
    summary="新增 RBAC 角色继承",
    description="管理员把子角色或用户绑定到父角色，例如把用户加入 admin。",
)
async def create_rbac_role(
    request: RbacRoleCreateRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/roles/create", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacPolicyListResponse:
    """新增角色继承并重载授权引擎。

    Args:
        request: 角色继承参数。
        actor: 当前鉴权主体。
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 更新后的完整策略视图。
    """
    await store.add_role(request.child, request.parent)
    reload_enforcer()
    return await _build_snapshot(store)


@router.post(
    "/roles/delete",
    response_model=RbacPolicyListResponse,
    summary="删除 RBAC 角色继承",
    description="管理员移除子角色或用户与父角色的绑定关系。",
)
async def delete_rbac_role(
    request: RbacRoleDeleteRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/roles/delete", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacPolicyListResponse:
    """删除角色继承并重载授权引擎。

    Args:
        request: 角色继承参数。
        actor: 当前鉴权主体。
        store: 策略存储。

    Returns:
        RbacPolicyListResponse: 更新后的完整策略视图。

    Raises:
        HTTPException: 角色关系不存在时返回 404。
    """
    deleted = await store.delete_role(request.child, request.parent)
    if not deleted:
        raise HTTPException(status_code=404, detail="角色关系不存在。")
    reload_enforcer()
    return await _build_snapshot(store)
