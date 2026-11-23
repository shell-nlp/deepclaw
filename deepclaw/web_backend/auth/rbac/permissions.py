"""受保护功能的 RBAC 权限目录。

目录项必须对应后端实际使用 require_permission 的路由；未受后端权限守卫保护的功能
不能出现在可配置目录里，避免 UI 显示可控、服务端却不执行鉴权。
"""

from deepclaw.web_backend.auth.rbac.schemas import (
    RbacPermissionDefinitionResponse,
    RbacPermissionRuleResponse,
)

PERMISSION_DEFINITIONS = (
    RbacPermissionDefinitionResponse(
        code="users.view",
        group="用户管理",
        name="查看用户",
        description="查看系统用户列表和账号资料。",
        rules=[RbacPermissionRuleResponse(path="/api/auth/users/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="users.manage",
        group="用户管理",
        name="管理用户",
        description="创建、编辑、停用、删除用户及重置密码。",
        rules=[RbacPermissionRuleResponse(path="/api/auth/users/*", action="write")],
    ),
    RbacPermissionDefinitionResponse(
        code="roles.view",
        group="角色管理",
        name="查看角色",
        description="查看角色目录、角色权限与授权策略。",
        rules=[RbacPermissionRuleResponse(path="/api/auth/rbac/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="roles.manage",
        group="角色管理",
        name="管理角色",
        description="新建角色、配置权限和维护授权策略。",
        rules=[RbacPermissionRuleResponse(path="/api/auth/rbac/*", action="write")],
    ),
    RbacPermissionDefinitionResponse(
        code="models.view",
        group="模型管理",
        name="查看模型",
        description="查看模型目录和模型详情。",
        rules=[
            RbacPermissionRuleResponse(path="/api/models/catalog", action="read"),
            RbacPermissionRuleResponse(path="/api/models/*", action="read"),
        ],
    ),
    RbacPermissionDefinitionResponse(
        code="models.manage",
        group="模型管理",
        name="管理模型",
        description="新增、编辑、删除、测试和切换模型。",
        rules=[
            RbacPermissionRuleResponse(path="/api/models", action="write"),
            RbacPermissionRuleResponse(path="/api/models/*", action="write"),
        ],
    ),
)


def list_permission_definitions() -> list[RbacPermissionDefinitionResponse]:
    """返回具有实际后端守卫的权限目录。

    Returns:
        按代码定义顺序排列的受保护功能权限。
    """
    return list(PERMISSION_DEFINITIONS)


LEGACY_PERMISSION_PAIRS = {
    ('/api/rag/*', 'read'), ('/api/rag/*', 'write'),
    ('/api/agui/*', 'read'), ('/api/agui/*', 'write'),
    ('/api/agent/*', 'read'), ('/api/agent/*', 'write'),
    ('/api/channels/*', 'read'), ('/api/channels/*', 'write'),
    ('/api/devices/*', 'read'), ('/api/devices/*', 'write'),
}

def allowed_permission_pairs() -> set[tuple[str, str]]:
    """返回目录项映射的真实 Casbin 路径动作白名单。

    Returns:
        角色权限 API 可写入的路径动作集合。
    """
    return LEGACY_PERMISSION_PAIRS | {
        (rule.path, rule.action)
        for definition in PERMISSION_DEFINITIONS
        for rule in definition.rules
    }
