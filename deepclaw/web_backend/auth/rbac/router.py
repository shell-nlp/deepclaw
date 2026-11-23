from fastapi import APIRouter, Depends, HTTPException, Response

from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac import reload_enforcer, require_permission
from deepclaw.web_backend.auth.rbac.schemas import (
    RbacCatalogCreateRequest,
    RbacCatalogListResponse,
    RbacCatalogPermissionResponse,
    RbacCatalogPermissionsRequest,
    RbacCatalogRoleResponse,
    RbacCatalogUpdateRequest,
    RbacPolicyCreateRequest,
    RbacPolicyDeleteRequest,
    RbacPolicyItemResponse,
    RbacPolicyListResponse,
    RbacRoleCreateRequest,
    RbacRoleDeleteRequest,
    RbacRoleItemResponse,
)
from deepclaw.web_backend.auth.rbac.store import (
    BUILTIN_ROLES,
    RbacPolicyStore,
    RoleCatalogError,
    get_rbac_policy_store,
)


router = APIRouter(prefix="/api/auth/rbac", tags=["rbac"])


def _require_catalog_writable() -> None:
    """禁用数据库策略时拒绝无效的目录写操作。

    Args:
        无。
    """
    if not settings.RBAC_STORE_ENABLED:
        raise HTTPException(status_code=409, detail="数据库 RBAC 策略未启用，无法修改角色目录。")


async def _catalog_response(store: RbacPolicyStore) -> RbacCatalogListResponse:
    """生成含实际用户数量与直接权限的角色目录。

    Args:
        store: RBAC 持久化存储。
    """
    roles = await store.list_catalog_roles()
    policies = await store.list_policies()
    permissions = {}
    for policy in policies:
        permissions.setdefault(policy.subject, []).append(
            RbacCatalogPermissionResponse(path=policy.path, action=policy.action)
        )
    return RbacCatalogListResponse(
        roles=[
            RbacCatalogRoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                builtin=role.id in BUILTIN_ROLES,
                user_count=await store.count_catalog_users(role.id),
                permissions=permissions.get(role.id, []),
            )
            for role in roles
        ]
    )


async def _catalog_item(store: RbacPolicyStore, role_id: str) -> RbacCatalogRoleResponse:
    """返回新建或修改后的角色目录项。

    Args:
        store: RBAC 持久化存储。
        role_id: 角色标识。
    """
    snapshot = await _catalog_response(store)
    for role in snapshot.roles:
        if role.id == role_id:
            return role
    raise HTTPException(status_code=404, detail="角色不存在。")


@router.get("/catalog/roles", response_model=RbacCatalogListResponse)
async def list_catalog_roles(
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/catalog/roles", "read")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacCatalogListResponse:
    """仅向具备策略授权的主体展示角色目录。

    Args:
        actor: 当前主体。
        store: 角色存储。
    """
    return await _catalog_response(store)


@router.post("/catalog/roles", response_model=RbacCatalogRoleResponse, status_code=201)
async def create_catalog_role(
    request: RbacCatalogCreateRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/catalog/roles", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacCatalogRoleResponse:
    """创建具有稳定标识的新角色。

    Args:
        request: 新角色资料。
        actor: 当前主体。
        store: 角色存储。
    """
    _require_catalog_writable()
    try:
        await store.create_catalog_role(request.id, request.name, request.description)
    except RoleCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return await _catalog_item(store, request.id)


@router.patch("/catalog/roles/{role_id}", response_model=RbacCatalogRoleResponse)
async def update_catalog_role(
    role_id: str,
    request: RbacCatalogUpdateRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/catalog/roles", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacCatalogRoleResponse:
    """只修改自建角色名称和说明，保持策略标识不变。

    Args:
        role_id: 角色标识。
        request: 修改资料。
        actor: 当前主体。
        store: 角色存储。
    """
    _require_catalog_writable()
    try:
        await store.update_catalog_role(role_id, request.name, request.description)
    except RoleCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return await _catalog_item(store, role_id)


@router.delete("/catalog/roles/{role_id}", status_code=204)
async def delete_catalog_role(
    role_id: str,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/catalog/roles", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> Response:
    """校验角色未在使用后删除目录及旧 p/g 策略。

    Args:
        role_id: 角色标识。
        actor: 当前主体。
        store: 角色存储。
    """
    _require_catalog_writable()
    try:
        count = await store.count_catalog_users(role_id)
        await store.delete_catalog_role(role_id, user_count=count)
    except RoleCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    reload_enforcer()
    return Response(status_code=204)


@router.put("/catalog/roles/{role_id}/permissions", response_model=RbacCatalogRoleResponse)
async def replace_catalog_permissions(
    role_id: str,
    request: RbacCatalogPermissionsRequest,
    actor: CurrentActor = Depends(require_permission("/api/auth/rbac/catalog/roles", "write")),
    store: RbacPolicyStore = Depends(get_rbac_policy_store),
) -> RbacCatalogRoleResponse:
    """原子替换自建角色的全部直接权限并重载授权引擎。

    Args:
        role_id: 角色标识。
        request: 全量权限集合。
        actor: 当前主体。
        store: 角色存储。
    """
    _require_catalog_writable()
    try:
        await store.replace_catalog_permissions(role_id, [(item.path, item.action) for item in request.permissions])
    except RoleCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    reload_enforcer()
    return await _catalog_item(store, role_id)


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
            RbacPolicyItemResponse(subject=rule.subject, path=rule.path, action=rule.action) for rule in policies
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
