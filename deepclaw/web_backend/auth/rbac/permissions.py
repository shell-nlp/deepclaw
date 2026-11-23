"""受保护功能的 RBAC 权限目录。

每个目录项都对应后端真实使用 require_permission 的路由；未加权限守卫的功能不能
出现在目录里，避免 UI 显示可控、服务端却不执行鉴权。
"""

from deepclaw.web_backend.auth.rbac.schemas import (
    RbacPermissionDefinitionResponse,
    RbacPermissionRuleResponse,
)

PERMISSION_DEFINITIONS = (
    RbacPermissionDefinitionResponse(
        code="knowledge.view",
        group="知识库",
        name="查看知识库",
        description="查看知识库、文档与切片。",
        rules=[RbacPermissionRuleResponse(path="/api/rag/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="knowledge.manage",
        group="知识库",
        name="管理知识库",
        description="创建知识库、上传文件、修改与删除内容。",
        rules=[RbacPermissionRuleResponse(path="/api/rag/*", action="write")],
    ),
    RbacPermissionDefinitionResponse(
        code="skills.view",
        group="能力与连接",
        name="查看技能",
        description="查看当前可用的技能包。",
        rules=[RbacPermissionRuleResponse(path="/api/agent/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="skills.manage",
        group="能力与连接",
        name="管理技能",
        description="上传和删除技能包。",
        rules=[RbacPermissionRuleResponse(path="/api/agent/*", action="write")],
    ),
    RbacPermissionDefinitionResponse(
        code="channels.view",
        group="能力与连接",
        name="查看渠道",
        description="查看渠道绑定与消息任务。",
        rules=[RbacPermissionRuleResponse(path="/api/channels/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="channels.manage",
        group="能力与连接",
        name="管理渠道",
        description="创建、编辑、删除渠道绑定并处理消息任务。",
        rules=[RbacPermissionRuleResponse(path="/api/channels/*", action="write")],
    ),
    RbacPermissionDefinitionResponse(
        code="devices.view",
        group="能力与连接",
        name="查看设备",
        description="查看已配对设备与设备任务。",
        rules=[RbacPermissionRuleResponse(path="/api/devices/*", action="read")],
    ),
    RbacPermissionDefinitionResponse(
        code="devices.manage",
        group="能力与连接",
        name="管理设备",
        description="配对、撤销设备并取消设备任务。",
        rules=[RbacPermissionRuleResponse(path="/api/devices/*", action="write")],
    ),
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
            RbacPermissionRuleResponse(path="/api/models", action="read"),
            RbacPermissionRuleResponse(path="/api/models/catalog", action="read"),
        ],
    ),
    RbacPermissionDefinitionResponse(
        code="models.manage",
        group="模型管理",
        name="管理模型",
        description="新增、编辑、删除、测试和切换模型。",
        rules=[RbacPermissionRuleResponse(path="/api/models", action="write")],
    ),
)


def list_permission_definitions() -> list[RbacPermissionDefinitionResponse]:
    """返回具有实际后端守卫的权限目录。

    Returns:
        按代码定义顺序排列的受保护功能权限。
    """
    return list(PERMISSION_DEFINITIONS)


def allowed_permission_pairs() -> set[tuple[str, str]]:
    """返回目录项映射的真实 Casbin 路径动作白名单。

    Returns:
        角色权限 API 可写入的路径动作集合。
    """
    return {
        (rule.path, rule.action)
        for definition in PERMISSION_DEFINITIONS
        for rule in definition.rules
    }


def matches_rule_path(rule_path: str, request_path: str) -> bool:
    """按 Casbin keyMatch 语义判断路径是否命中规则。

    Args:
        rule_path: 策略中的路径规则，支持结尾通配符星号。
        request_path: 具体请求路径。

    Returns:
        bool: 命中时返回真。
    """
    if rule_path.endswith("*"):
        return request_path.startswith(rule_path[:-1])
    return rule_path == request_path
