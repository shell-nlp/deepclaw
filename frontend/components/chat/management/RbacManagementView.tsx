'use client'

import { useEffect, useMemo, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { RbacPolicyItem, RbacRoleItem } from '../utils/types'

interface RbacManagementViewProps {
  canManage: boolean
  policies: RbacPolicyItem[]
  roles: RbacRoleItem[]
  loading: boolean
  busy: boolean
  notice: string
  error: string
  policyDraft: { subject: string; path: string; action: string }
  roleDraft: { child: string; parent: string }
  onPolicyDraftChange: (draft: { subject: string; path: string; action: string }) => void
  onRoleDraftChange: (draft: { child: string; parent: string }) => void
  onLoadPolicies: () => void | Promise<void>
  onCreatePolicy: () => void | Promise<void>
  onDeletePolicy: (policy: RbacPolicyItem) => void | Promise<void>
  onCreateRole: () => void | Promise<void>
  onDeleteRole: (role: RbacRoleItem) => void | Promise<void>
}

interface PolicyGroup {
  subject: string
  items: RbacPolicyItem[]
}

/**
 * 按主体归并策略，并按主体名称升序返回分组结果。
 * @param policies 当前需要展示的策略列表
 * @returns 以主体为分组的策略集合
 */
function groupPoliciesBySubject(policies: RbacPolicyItem[]): PolicyGroup[] {
  const grouped = new Map<string, RbacPolicyItem[]>()
  policies.forEach((policy) => {
    const bucket = grouped.get(policy.subject)
    if (bucket) {
      bucket.push(policy)
    } else {
      grouped.set(policy.subject, [policy])
    }
  })
  return Array.from(grouped.entries())
    .sort(([left], [right]) => left.localeCompare(right, 'zh-Hans-CN'))
    .map(([subject, items]) => ({ subject, items }))
}

/**
 * 返回动作徽标对应的样式组合，未知动作回退为中性样式。
 * @param action 策略中的动作值，例如 read 或 write
 * @returns 动作徽标的 className
 */
const RESOURCE_LABELS: Array<{ path: string; label: string; detail: string }> = [
  { path: '/api/agui/*', label: '对话与智能体', detail: '对话、运行、线程和智能体能力' },
  { path: '/api/rag/*', label: '知识库', detail: '知识库、文档与切片' },
  { path: '/api/agent/*', label: '技能与工具', detail: '技能、工具与 Agent 扩展' },
  { path: '/api/channels/*', label: '渠道管理', detail: '飞书、微信等渠道绑定' },
  { path: '/api/devices/*', label: '设备管理', detail: '设备配对与设备任务' },
  { path: '/api/auth/users/*', label: '用户管理', detail: '账号、状态与密码' },
  { path: '/api/auth/rbac/*', label: '角色与权限', detail: '角色继承与权限策略' },
  { path: '/api/models/*', label: '模型管理', detail: '大模型与语义模型' },
  { path: '/api/models', label: '模型目录', detail: '模型目录入口权限' },
]

function resourceLabel(path: string): { label: string; detail: string } {
  return RESOURCE_LABELS.find((item) => item.path === path) || {
    label: '自定义资源',
    detail: path,
  }
}

function actionLabel(action: string): string {
  return action === 'read' ? '查看' : action === 'write' ? '管理' : action
}


interface PolicyResourceGroup {
  path: string
  policies: RbacPolicyItem[]
}

function groupPoliciesByResource(items: RbacPolicyItem[]): PolicyResourceGroup[] {
  const grouped = new Map<string, RbacPolicyItem[]>()
  items.forEach((policy) => {
    const bucket = grouped.get(policy.path)
    if (bucket) bucket.push(policy)
    else grouped.set(policy.path, [policy])
  })
  return Array.from(grouped.entries()).map(([path, policies]) => ({ path, policies }))
}

function actionBadgeClassName(action: string): string {
  if (action === 'read') return `${styles.rbacAction} ${styles.rbacActionRead}`
  if (action === 'write') return `${styles.rbacAction} ${styles.rbacActionWrite}`
  return `${styles.rbacAction} ${styles.rbacActionOther}`
}

/**
 * 绘制行尾删除按钮使用的图标。
 * @returns 继承 currentColor 的垃圾桶图标
 */
function DeleteIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M2.5 4.5h11M6.5 4.5V3.3c0-.4.3-.8.8-.8h1.4c.5 0 .8.4.8.8v1.2M4.2 4.5l.6 8.1c0 .5.4.9.9.9h4.6c.5 0 .9-.4.9-.9l.6-8.1"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.3"
      />
    </svg>
  )
}

/**
 * 角色与角色权限管理工作区：左侧维护角色与继承链，右侧按主体分组管理角色权限。
 * 组件只编排视图状态，所有数据加载与写操作仍由外部传入的回调完成。
 * @param props 角色、策略、草稿与全部业务回调，语义与 useRbacPolicies 保持一致
 * @returns 角色管理视图
 */
export function RbacManagementView({
  canManage,
  policies,
  roles,
  loading,
  busy,
  notice,
  error,
  policyDraft,
  roleDraft,
  onPolicyDraftChange,
  onRoleDraftChange,
  onLoadPolicies,
  onCreatePolicy,
  onDeletePolicy,
  onCreateRole,
  onDeleteRole,
}: RbacManagementViewProps) {
  const [search, setSearch] = useState('')
  const [subjectFilter, setSubjectFilter] = useState('all')
  const [expandedPolicies, setExpandedPolicies] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (canManage) void onLoadPolicies()
  }, [canManage, onLoadPolicies])

  const subjects = useMemo(
    () =>
      Array.from(new Set(policies.map((policy) => policy.subject))).sort((left, right) =>
        left.localeCompare(right, 'zh-Hans-CN')
      ),
    [policies]
  )

  const visiblePolicies = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase()
    return policies.filter((policy) => {
      if (subjectFilter !== 'all' && policy.subject !== subjectFilter) return false
      if (!keyword) return true
      return policy.path.toLocaleLowerCase().includes(keyword)
    })
  }, [policies, search, subjectFilter])

  const policyGroups = useMemo(
    () => groupPoliciesBySubject(visiblePolicies),
    [visiblePolicies]
  )

  const subjectCount = subjects.length
  const filtersActive = search.trim().length > 0 || subjectFilter !== 'all'

  /**
   * 清空主体筛选与路径关键词，恢复展示全部策略。
   */
  const resetFilters = () => {
    setSearch('')
    setSubjectFilter('all')
  }

  if (!canManage) {
    return (
      <div className={styles.managementPage}>
        <div className={styles.managementTopbar}>
          <div className={styles.managementRouteInfo}>
            <span className={styles.managementBreadcrumb}>系统 / 角色管理</span>
            <h2>角色管理</h2>
            <p>角色与继承与角色权限仅对管理员开放。</p>
          </div>
          <div className={styles.managementTopbarMeta}>
            <span className={styles.managementMeta}>只读提示</span>
          </div>
        </div>
        <section
          className={`${styles.rbacPanel} ${styles.rbacRestricted}`}
          aria-labelledby="rbac-restricted-title"
        >
          <div className={styles.rbacPanelHeader}>
            <div className={styles.rbacPanelHeading}>
              <h3 id="rbac-restricted-title">角色权限</h3>
              <p className={styles.rbacPanelHint}>
                角色与角色权限由管理员维护。普通用户可以继续使用聊天、知识库和技能功能。
              </p>
            </div>
            <span className={styles.rbacTag}>仅管理员</span>
          </div>
          <div className={styles.rbacPanelBody}>
            <div className={styles.rbacEmpty}>
              <strong>当前账号没有管理权限</strong>
              <span>请使用管理员账号登录后查看角色与继承与策略清单。</span>
            </div>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className={styles.managementPage}>
      <div className={styles.managementTopbar}>
        <div className={styles.managementRouteInfo}>
          <span className={styles.managementBreadcrumb}>系统 / 角色管理</span>
          <h2>角色管理</h2>
          <p>角色决定谁能看到什么资源；继承关系让权限按层级复用，而不是逐条重复授权。</p>
        </div>
        <div className={styles.rbacStats} role="group" aria-label="角色权限统计">
          <div className={styles.rbacStat}>
            <span className={styles.rbacStatValue}>{policies.length}</span>
            <span className={styles.rbacStatLabel}>条策略</span>
          </div>
          <div className={styles.rbacStat}>
            <span className={styles.rbacStatValue}>{subjectCount}</span>
            <span className={styles.rbacStatLabel}>个角色 / 用户</span>
          </div>
        </div>
      </div>

      {notice || error ? (
        <div className={styles.managementNoticeRow}>
          {notice ? (
            <div className={styles.managementNotice} role="status">
              {notice}
            </div>
          ) : null}
          {error ? (
            <div className={styles.managementError} role="alert">
              {error}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className={styles.rbacGuide} aria-label="角色配置流程">
        <div className={styles.rbacGuideStep}><strong>1</strong><div><b>先建角色</b><span>左侧输入新角色名，例如 analyst</span></div></div>
        <div className={styles.rbacGuideArrow} aria-hidden="true">→</div>
        <div className={styles.rbacGuideStep}><strong>2</strong><div><b>再配权限</b><span>右侧给角色设置路径和 read / write</span></div></div>
        <div className={styles.rbacGuideArrow} aria-hidden="true">→</div>
        <div className={styles.rbacGuideStep}><strong>3</strong><div><b>分配给用户</b><span>左侧输入 user_xxx 继承 analyst</span></div></div>
      </div>

      <div className={styles.rbacWorkspace}>
        <aside
          className={`${styles.rbacPanel} ${styles.rbacRolePanel}`}
          aria-labelledby="rbac-roles-title"
          aria-busy={loading || busy}
        >
          <div className={styles.rbacPanelHeader}>
            <div className={styles.rbacPanelHeading}>
              <h3 id="rbac-roles-title">
                角色与继承
                <span className={styles.rbacCount}>{roles.length}</span>
              </h3>
              <p className={styles.rbacPanelHint}>
                输入新名称即可建立角色；输入用户 ID 可把账号分配到角色。子角色会继承父角色的权限。
              </p>
            </div>
          </div>
          <div className={styles.rbacPanelBody}>
            {roles.length === 0 ? (
              <div className={styles.rbacEmpty}>
                <strong>还没有继承关系</strong>
                <span>在下方添加第一条关系，例如把用户挂到 user 角色。</span>
              </div>
            ) : (
              <ul className={styles.rbacRoleList} role="list">
                {roles.map((role) => (
                  <li key={`${role.child}->${role.parent}`} className={styles.rbacRoleRow}>
                    <span className={styles.rbacRoleChain}>
                      <span className={styles.rbacRoleChild} title={role.child}>
                        {role.child}
                      </span>
                      <span className={styles.rbacRoleArrow} aria-hidden="true">
                        →
                      </span>
                      <span className={styles.rbacRoleParent} title={role.parent}>
                        {role.parent}
                      </span>
                    </span>
                    <button
                      type="button"
                      className={styles.rbacIconButton}
                      disabled={busy}
                      onClick={() => void onDeleteRole(role)}
                      aria-label={`移除继承关系：${role.child} 继承 ${role.parent}`}
                      title="移除继承关系"
                    >
                      <DeleteIcon />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <form
            className={styles.rbacForm}
            onSubmit={(event) => {
              event.preventDefault()
              if (!busy) void onCreateRole()
            }}
          >
            <span className={styles.rbacFormTitle}>创建角色或分配用户</span>
            <div className={styles.rbacRoleFormGrid}>
              <label className={styles.rbacField} htmlFor="rbac-role-child">
                <span className={styles.rbacFieldLabel}>角色名或用户 ID</span>
                <input
                  id="rbac-role-child"
                  className={styles.rbacInput}
                  value={roleDraft.child}
                  onChange={(event) =>
                    onRoleDraftChange({ ...roleDraft, child: event.target.value })
                  }
                  placeholder="例如 analyst 或 user_xxx"
                  autoComplete="off"
                />
              </label>
              <span className={styles.rbacFormArrow} aria-hidden="true">
                →
              </span>
              <label className={styles.rbacField} htmlFor="rbac-role-parent">
                <span className={styles.rbacFieldLabel}>父角色</span>
                <input
                  id="rbac-role-parent"
                  className={styles.rbacInput}
                  value={roleDraft.parent}
                  onChange={(event) =>
                    onRoleDraftChange({ ...roleDraft, parent: event.target.value })
                  }
                  placeholder="继承自哪个角色？例如 user"
                  autoComplete="off"
                />
              </label>
            </div>
            <button type="submit" className={styles.rbacButton} disabled={busy}>
              创建 / 分配
            </button>
          </form>
        </aside>

        <section
          className={styles.rbacPanel}
          aria-labelledby="rbac-policies-title"
          aria-busy={loading || busy}
        >
          <div className={styles.rbacPanelHeader}>
            <div className={styles.rbacPanelHeading}>
              <h3 id="rbac-policies-title">
                角色权限
                <span className={styles.rbacCount}>{policies.length}</span>
              </h3>
              <p className={styles.rbacPanelHint}>
                路径使用 Casbin keyMatch 规则，例如{' '}
                <code className={styles.rbacCode}>/api/rag/*</code>{' '}
                匹配知识库全部接口；修改后立即生效，无需重启服务。
              </p>
            </div>
            <span className={styles.rbacPanelMeta}>
              {loading
                ? '读取中…'
                : filtersActive
                  ? `显示 ${visiblePolicies.length} / ${policies.length} 条`
                  : '按主体分组'}
            </span>
          </div>

          <div className={styles.rbacToolbar}>
            <input
              className={`${styles.rbacInput} ${styles.rbacToolbarSearch}`}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="按路径筛选，例如 /api/rag/*"
              aria-label="按路径筛选角色权限"
              autoComplete="off"
            />
            <select
              className={`${styles.rbacSelect} ${styles.rbacToolbarSelect}`}
              value={subjectFilter}
              onChange={(event) => setSubjectFilter(event.target.value)}
              aria-label="按主体筛选角色权限"
            >
              <option value="all">全部主体</option>
              {subjects.map((subject) => (
                <option key={subject} value={subject}>
                  {subject}
                </option>
              ))}
            </select>
            <div className={styles.rbacToolbarActions}>
              <button
                type="button"
                className={styles.rbacButtonGhost}
                disabled={loading}
                onClick={() => void onLoadPolicies()}
              >
                刷新
              </button>
            </div>
          </div>

          <div className={`${styles.rbacPanelBody} ${styles.rbacPolicyBody}`}>
            {loading && policies.length === 0 ? (
              <div className={styles.rbacEmpty}>
                <strong>正在读取策略</strong>
                <span>稍候即可看到按主体分组的权限清单。</span>
              </div>
            ) : policyGroups.length === 0 ? (
              <div className={styles.rbacEmpty}>
                <strong>
                  {filtersActive ? '没有匹配的策略' : '还没有配置策略'}
                </strong>
                <span>
                  {filtersActive
                    ? '换一个主体或路径关键词，或者清除筛选查看全部策略。'
                    : '在下方新增第一条策略，为主体授予路径上的读写权限。'}
                </span>
                {filtersActive ? (
                  <button
                    type="button"
                    className={styles.rbacButtonGhost}
                    onClick={resetFilters}
                  >
                    清除筛选
                  </button>
                ) : null}
              </div>
            ) : (
              policyGroups.map((group) => (
                <div key={group.subject} className={styles.rbacGroup}>
                  <div className={styles.rbacGroupHead}>
                    <span className={styles.rbacGroupSubject}>{group.subject}</span>
                    <span className={styles.rbacGroupCount}>{group.items.length} 条</span>
                    <span className={styles.rbacGroupRule} aria-hidden="true" />
                  </div>
                  <ul className={styles.rbacPolicyList} role="list">
                    {groupPoliciesByResource(group.items).map((resource) => {
                      const resourceKey = group.subject + '|' + resource.path
                      const isExpanded = expandedPolicies.has(resourceKey)
                      return (
                        <li key={resourceKey} className={styles.rbacPolicyRow + ' ' + (isExpanded ? styles.rbacPolicyRowExpanded : '')}>
                          <button
                            type="button"
                            className={styles.rbacPolicyResource}
                            onClick={() => setExpandedPolicies((current) => {
                              const next = new Set(current)
                              if (next.has(resourceKey)) next.delete(resourceKey)
                              else next.add(resourceKey)
                              return next
                            })}
                            aria-expanded={isExpanded}
                          >
                            <span className={styles.rbacPolicyResourceName}>{resourceLabel(resource.path).label}</span>
                            <span className={styles.rbacPolicyResourceDetail}>{resourceLabel(resource.path).detail}</span>
                            {isExpanded ? <code className={styles.rbacPolicyPath}>{resource.path}</code> : null}
                          </button>
                          <span className={styles.rbacResourcePermissionCount}>{resource.policies.length} 项权限</span>
                          <span className={styles.rbacResourceChevron} aria-hidden="true">{isExpanded ? '⌃' : '⌄'}</span>
                          {isExpanded ? (
                            <div className={styles.rbacResourceActions}>
                              {resource.policies.map((policy) => (
                                <div key={policy.action} className={styles.rbacPermissionChip}>
                                  <span className={actionBadgeClassName(policy.action)}>{actionLabel(policy.action)}</span>
                                  <button type="button" className={styles.rbacIconButton} disabled={busy} onClick={() => void onDeletePolicy(policy)} aria-label={'删除' + actionLabel(policy.action) + '权限'} title="删除权限"><DeleteIcon /></button>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))
            )}
          </div>

          <form
            className={styles.rbacPolicyForm}
            aria-label="为角色配置权限"
            onSubmit={(event) => {
              event.preventDefault()
              if (!busy) void onCreatePolicy()
            }}
          >
            <div className={styles.rbacFormTitle}>为角色添加权限</div>
            <p className={styles.rbacFormHint}>例如：角色 analyst + /api/rag/* + read</p>
            <label className={styles.rbacField} htmlFor="rbac-policy-subject">
              <span className={styles.rbacFieldLabel}>角色 / 用户</span>
              <input
                id="rbac-policy-subject"
                className={styles.rbacInput}
                value={policyDraft.subject}
                onChange={(event) =>
                  onPolicyDraftChange({ ...policyDraft, subject: event.target.value })
                }
                placeholder="例如 analyst / admin / user_xxx"
                autoComplete="off"
              />
            </label>
            <label className={styles.rbacField} htmlFor="rbac-policy-path">
              <span className={styles.rbacFieldLabel}>功能资源</span>
              <select
                id="rbac-policy-path"
                className={styles.rbacSelect}
                value={policyDraft.path}
                onChange={(event) =>
                  onPolicyDraftChange({ ...policyDraft, path: event.target.value })
                }
              >
                {RESOURCE_LABELS.map((resource) => (
                  <option key={resource.path} value={resource.path}>
                    {resource.label} · {resource.detail}
                  </option>
                ))}
                {!RESOURCE_LABELS.some((resource) => resource.path === policyDraft.path) && policyDraft.path ? (
                  <option value={policyDraft.path}>自定义资源 · {policyDraft.path}</option>
                ) : null}
              </select>
            </label>
            <label className={styles.rbacField} htmlFor="rbac-policy-action">
              <span className={styles.rbacFieldLabel}>动作</span>
              <select
                id="rbac-policy-action"
                className={styles.rbacSelect}
                value={policyDraft.action}
                onChange={(event) =>
                  onPolicyDraftChange({ ...policyDraft, action: event.target.value })
                }
              >
                <option value="read">read</option>
                <option value="write">write</option>
              </select>
            </label>
            <button type="submit" className={styles.rbacButton} disabled={busy}>
              添加策略
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}
