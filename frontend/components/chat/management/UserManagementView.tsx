'use client'

import { useCallback, useEffect, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { ActorState } from '../utils/auth'
import type { AuthUserSummary, RoleCatalogRecord, RoleCatalogResponse } from '../utils/types'
import { RBAC_ROLE_CATALOG_API_PATH } from '../utils/constants'

interface UserManagementViewProps {
  actor: ActorState
  users: AuthUserSummary[]
  loading: boolean
  notice: string
  error: string
  onOpenAuth: () => void
  onLoadUsers: (search: string) => void | Promise<void>
  onCreateUser: (input: { username: string; password: string; role: string; display_name?: string }) => Promise<boolean>
  onUpdateUserRole: (userId: string, role: string) => void | Promise<void>
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  canManageUsers?: boolean
  onUpdateUserStatus: (userId: string, isActive: boolean) => void | Promise<void>
  onUpdateUserProfile: (
    userId: string,
    input: { username?: string; email?: string; display_name?: string }
  ) => Promise<boolean>
  onDeleteUser: (userId: string) => void | Promise<void>
  onResetUserPassword: (userId: string, password: string) => void | Promise<void>
  currentUserId?: string
}

/**
 * 管理员用户管理工作区，集中展示账号列表并通过弹窗承载创建操作。
 * 保留用户管理的全部业务回调，视图层只负责表单状态和交互编排。
 */
function formatAccountTime(value?: string | null): string {
  if (!value) return '未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function UserManagementView({
  actor,
  users,
  loading,
  notice,
  error,
  onOpenAuth,
  onLoadUsers,
  requestJson,
  canManageUsers = actor.role === 'admin',
  onCreateUser,
  onUpdateUserRole,
  onUpdateUserStatus,
  onUpdateUserProfile,
  onDeleteUser,
  onResetUserPassword,
  currentUserId,
}: UserManagementViewProps) {
  const [search, setSearch] = useState('')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')
  const [roleOptions, setRoleOptions] = useState<RoleCatalogRecord[]>([])
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AuthUserSummary | null>(null)
  const [editUsername, setEditUsername] = useState('')
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editEmail, setEditEmail] = useState('')

  useEffect(() => {
    if (!actor.isGuest && canManageUsers) void onLoadUsers('')
  }, [actor.isGuest, canManageUsers, onLoadUsers])

  const loadRoles = useCallback(async () => {
    if (actor.isGuest || !canManageUsers) return
    try {
      const response = await requestJson<RoleCatalogResponse>(RBAC_ROLE_CATALOG_API_PATH)
      setRoleOptions(response.roles)
    } catch {
      setRoleOptions([])
    }
  }, [actor.isGuest, canManageUsers, requestJson])

  useEffect(() => { void loadRoles() }, [loadRoles])

  if (actor.isGuest) {
    return (
      <div className={styles.managementPage}>
        <div className={styles.managementTopbar}>
          <div className={styles.managementRouteInfo}>
            <span className={styles.managementBreadcrumb}>系统 / 用户管理</span><h2>用户管理</h2>
            <p>游客模式下可先浏览系统，登录后可进入账号中心；只有管理员可以管理用户。</p>
          </div>
        </div>
        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
            <div className={styles.managementHeader}><h3>当前身份</h3><span className={styles.accountRoleBadge}>游客</span></div>
            <p className={styles.managementDescription}>你现在使用的是默认游客账户。技能管理与知识库管理均已对游客开放，只有用户管理需要登录管理员账号。</p>
            <div className={styles.managementToolbar}><button type="button" className={styles.managementButton} onClick={onOpenAuth}>前往登录页</button></div>
          </section>
        </div>
      </div>
    )
  }

  if (!canManageUsers) {
    return (
      <div className={styles.managementPage}>
        <div className={styles.managementTopbar}><div className={styles.managementRouteInfo}>
          <span className={styles.managementBreadcrumb}>系统 / 用户管理</span><h2>用户管理</h2><p>当前账号已登录，但该页面仅对管理员开放。</p>
        </div></div>
        <div className={styles.managementPageGrid}><section className={styles.managementCard}>
          <div className={styles.managementHeader}><h3>当前账号</h3><span className={styles.accountRoleBadge}>普通用户</span></div>
          <div className={styles.managementMetaPanel}><span>显示名: {actor.displayName || actor.username || '-'}</span><span>用户名: {actor.username || '-'}</span><span>邮箱: {actor.email || '-'}</span><span>用户 ID: {actor.userId}</span></div>
          <p className={styles.managementDescription}>你可以继续使用聊天、知识库和技能功能；用户账号管理仅管理员可见。</p>
        </section></div>
      </div>
    )
  }

  const handleCreateUser = async () => {
    const created = await onCreateUser({ username, password, role, display_name: displayName.trim() })
    if (!created) return
    setUsername(''); setDisplayName(''); setPassword(''); setRole('user'); setIsCreateOpen(false)
  }

  return (
    <div className={styles.managementPage}>
      <div className={styles.managementNoticeRow}>
        {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
        {error ? <div className={styles.managementError}>{error}</div> : null}
      </div>
      <div className={styles.managementTopbar}>
        <div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 用户管理</span><h2>用户管理</h2><p>集中管理系统账号、角色与访问状态。</p></div>
        <div className={styles.managementTopbarMeta}><span className={styles.managementMeta}>管理员工作区</span></div>
      </div>
      <div className={styles.userManagementWorkspace}>
        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <div><h3>用户列表</h3><p className={styles.managementHelperText}>查看账号状态并快速调整权限。</p></div>
            <span className={styles.managementMeta}>{loading ? '加载中...' : '共 ' + users.length + ' 个账号'}</span>
          </div>
          <div className={styles.userManagementToolbar}>
            <div className={styles.managementSearchGroup}>
              <input className={styles.managementInput} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void onLoadUsers(search.trim()) }} placeholder="按用户名或邮箱搜索" aria-label="搜索用户" />
              <button type="button" className={styles.managementMinorButton} onClick={() => void onLoadUsers(search.trim())}>搜索</button>
            </div>
            <button type="button" className={styles.managementButton} onClick={() => setIsCreateOpen(true)}>创建用户</button>
          </div>
          <div className={styles.managementDataList}>
            {users.length === 0 ? <div className={styles.managementEmpty}>当前没有匹配的用户。</div> : users.map((user) => (
              <div key={user.user_id} className={styles.managementDataRow}>
                <div className={styles.managementDataPrimary}><div className={styles.managementDataTitle}><strong>{user.display_name || user.username}</strong>{user.display_name ? <span className={styles.managementMeta}>账号 {user.username}</span> : null}{user.email ? <span className={styles.managementMeta}>{user.email}</span> : null}<span className={styles.accountRoleBadge}>{roleOptions.find((item) => item.id === user.role)?.name || user.role}</span></div><span className={styles.managementDataDescription}>用户 ID: {user.user_id}</span><span className={styles.managementDataDescription}>创建：{formatAccountTime(user.created_at)} · 更新：{formatAccountTime(user.updated_at)}</span></div>
                <div className={styles.managementDataMetrics}><span className={user.is_active ? styles.userStatusActive : styles.userStatusInactive}><span aria-hidden="true" className={styles.userStatusDot} />{user.is_active ? '启用中' : '已停用'}</span></div>
                <div className={styles.managementDataActions}>
                  <button type="button" className={styles.managementMinorButton} onClick={() => { setEditingUser(user); setEditUsername(user.username || ''); setEditDisplayName(user.display_name || ''); setEditEmail(user.email || '') }} aria-label={`编辑 ${user.username} 的资料`}>编辑</button>
                  <label className={styles.managementField}>角色
                    <select className={styles.managementInput} aria-label={'设置 ' + user.username + ' 的角色'} value={user.role} onChange={(event) => void onUpdateUserRole(user.user_id, event.target.value)} disabled={user.user_id === currentUserId}>
                      {roleOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                      {!roleOptions.some((item) => item.id === user.role) && <option value={user.role}>{user.role}</option>}
                    </select>
                  </label>
                  <button type="button" className={styles.managementMinorButton} onClick={() => void onUpdateUserStatus(user.user_id, !user.is_active)}>{user.is_active ? '停用账号' : '启用账号'}</button>
                  <button type="button" className={styles.managementDangerMinorButton} onClick={() => { const nextPassword = window.prompt('为 ' + user.username + ' 设置新密码（至少 8 位）'); if (nextPassword) void onResetUserPassword(user.user_id, nextPassword) }}>重置密码</button>
                  <button type="button" className={styles.managementDangerMinorButton} disabled={user.user_id === currentUserId} title={user.user_id === currentUserId ? '不能删除当前登录账号' : undefined} onClick={() => { if (window.confirm('确定删除账号 ' + user.username + ' 吗？该操作不可恢复。')) void onDeleteUser(user.user_id) }} aria-label={`删除用户 ${user.username}`}>删除</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      {isCreateOpen ? (
        <div className={styles.managementModalOverlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsCreateOpen(false) }}>
          <section className={styles.managementModal} role="dialog" aria-modal="true" aria-labelledby="create-user-title">
            <div className={styles.managementHeader}><div><span className={styles.managementBreadcrumb}>账号设置</span><h3 id="create-user-title">创建用户</h3></div><button type="button" className={styles.managementModalClose} onClick={() => setIsCreateOpen(false)} aria-label="关闭创建用户窗口">关闭</button></div>
            <p className={styles.managementHelperText}>为新成员设置登录信息和访问角色，创建后可在列表中继续调整。</p>
            <div className={styles.managementForm}>
              <label className={styles.managementField}>用户名<input className={styles.managementInput} type="text" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="登录时使用的用户名" autoFocus /></label>
              <label className={styles.managementField}>显示名<input className={styles.managementInput} type="text" value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={64} placeholder="可选，留空时显示用户名" /></label>
              <label className={styles.managementField}>初始密码<input className={styles.managementInput} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位" /></label>
              <label className={styles.managementField}>角色<select className={styles.managementInput} value={role} onChange={(event) => setRole(event.target.value)}>{roleOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}{!roleOptions.length && <><option value="user">普通用户</option><option value="admin">管理员</option></>}</select></label>
              <div className={styles.managementToolbar}><button type="button" className={styles.managementMinorButton} onClick={() => setIsCreateOpen(false)}>取消</button><button type="button" className={styles.managementButton} onClick={() => void handleCreateUser()}>创建用户</button></div>
            </div>
          </section>
        </div>
      ) : null}
      {editingUser ? (
        <div className={styles.managementModalOverlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditingUser(null) }}>
          <section className={styles.managementModal} role="dialog" aria-modal="true" aria-labelledby="edit-user-title">
            <div className={styles.managementHeader}><div><span className={styles.managementBreadcrumb}>账号设置</span><h3 id="edit-user-title">编辑用户</h3></div><button type="button" className={styles.managementModalClose} onClick={() => setEditingUser(null)} aria-label="关闭编辑用户窗口">关闭</button></div>
            <p className={styles.managementHelperText}>可修改登录用户名、显示名和联系邮箱；密码请使用列表中的重置密码操作。</p>
            <div className={styles.managementForm}>
              <label className={styles.managementField}>用户名<input className={styles.managementInput} type="text" value={editUsername} onChange={(event) => setEditUsername(event.target.value)} autoFocus /></label>
              <label className={styles.managementField}>显示名<input className={styles.managementInput} type="text" value={editDisplayName} onChange={(event) => setEditDisplayName(event.target.value)} maxLength={64} placeholder="可选，留空时显示用户名" /></label>
              <label className={styles.managementField}>邮箱<input className={styles.managementInput} type="email" value={editEmail} onChange={(event) => setEditEmail(event.target.value)} placeholder="留空表示不填写" /></label>
              <div className={styles.managementToolbar}><button type="button" className={styles.managementMinorButton} onClick={() => setEditingUser(null)}>取消</button><button type="button" className={styles.managementButton} onClick={async () => { const saved = await onUpdateUserProfile(editingUser.user_id, { username: editUsername.trim(), email: editEmail.trim(), display_name: editDisplayName.trim() }); if (saved) setEditingUser(null) }}>保存修改</button></div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
