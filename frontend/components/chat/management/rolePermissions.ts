export interface PermissionChoice {
  path: string
  action: 'read' | 'write'
  group: string
  label: string
  detail: string
}

/** 按业务能力分组的授权项，与服务端实际策略路径对应。 */
export const PERMISSION_CHOICES: PermissionChoice[] = [
  { group: '对话', label: '查看对话与智能体', detail: '查看智能体、运行和会话', path: '/api/agui/*', action: 'read' },
  { group: '对话', label: '运行对话', detail: '创建、恢复和取消智能体运行', path: '/api/agui/*', action: 'write' },
  { group: '知识库', label: '查看知识库', detail: '查看知识库与文档', path: '/api/rag/*', action: 'read' },
  { group: '知识库', label: '管理知识库', detail: '上传、编辑和删除知识内容', path: '/api/rag/*', action: 'write' },
  { group: '能力与连接', label: '查看技能', detail: '查看技能列表', path: '/api/agent/*', action: 'read' },
  { group: '能力与连接', label: '管理技能', detail: '上传与删除技能', path: '/api/agent/*', action: 'write' },
  { group: '能力与连接', label: '查看渠道', detail: '查看渠道绑定', path: '/api/channels/*', action: 'read' },
  { group: '能力与连接', label: '管理渠道', detail: '配置、删除渠道绑定', path: '/api/channels/*', action: 'write' },
  { group: '能力与连接', label: '查看设备', detail: '查看设备状态与任务', path: '/api/devices/*', action: 'read' },
  { group: '能力与连接', label: '管理设备', detail: '配对或撤销设备', path: '/api/devices/*', action: 'write' },
  { group: '系统', label: '查看用户', detail: '查看用户列表', path: '/api/auth/users/*', action: 'read' },
  { group: '系统', label: '管理用户', detail: '创建、编辑和停用用户', path: '/api/auth/users/*', action: 'write' },
  { group: '系统', label: '查看角色', detail: '查看角色与权限配置', path: '/api/auth/rbac/*', action: 'read' },
  { group: '系统', label: '管理角色', detail: '新建角色并保存权限', path: '/api/auth/rbac/*', action: 'write' },
  { group: '系统', label: '查看模型目录', detail: '查看已配置的模型', path: '/api/models', action: 'read' },
  { group: '系统', label: '管理模型目录', detail: '新建、编辑和切换模型', path: '/api/models', action: 'write' },
  { group: '系统', label: '查看模型配置', detail: '查看模型详情', path: '/api/models/*', action: 'read' },
  { group: '系统', label: '管理模型配置', detail: '编辑模型配置', path: '/api/models/*', action: 'write' },
]

/** 标识一项权限，供矩阵勾选与差异计算使用。 */
export function permissionKey(path: string, action: string): string {
  return path + ':' + action
}
