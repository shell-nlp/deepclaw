'use client'

import { useEffect, useState } from 'react'

import styles from '../ChatInterface.module.css'
import type { ActorState } from './auth'
import type { AuthUserSummary } from './types'

interface UserManagementViewProps {
  actor: ActorState
  users: AuthUserSummary[]
  loading: boolean
  notice: string
  error: string
  onOpenAuth: () => void
  onLoadUsers: (search: string) => void | Promise<void>
  onCreateUser: (input: {
    email: string
    password: string
    role: 'admin' | 'user'
  }) => void | Promise<void>
  onUpdateUserRole: (
    userId: string,
    role: 'admin' | 'user'
  ) => void | Promise<void>
  onUpdateUserStatus: (
    userId: string,
    isActive: boolean
  ) => void | Promise<void>
  onResetUserPassword: (userId: string, password: string) => void | Promise<void>
}

export function UserManagementView({
  actor,
  users,
  loading,
  notice,
  error,
  onOpenAuth,
  onLoadUsers,
  onCreateUser,
  onUpdateUserRole,
  onUpdateUserStatus,
  onResetUserPassword,
}: UserManagementViewProps) {
  const [search, setSearch] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'user'>('user')

  useEffect(() => {
    if (!actor.isGuest && actor.role === 'admin') {
      void onLoadUsers('')
    }
  }, [actor.isGuest, actor.role, onLoadUsers])

  if (actor.isGuest) {
    return (
      <div className={styles.managementPage}>
        <div className={styles.managementTopbar}>
          <div className={styles.managementRouteInfo}>
            <span className={styles.managementBreadcrumb}>账号 / 用户管理</span>
            <h2>用户管理</h2>
            <p>游客模式下可先浏览系统，登录后可进入账号中心；只有管理员可以管理用户。</p>
          </div>
        </div>
        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>当前身份</h3>
              <span className={styles.accountRoleBadge}>游客</span>
            </div>
            <p className={styles.managementDescription}>
              你现在使用的是默认游客账户。知识库管理和技能管理中的写入操作会被禁用。
            </p>
            <div className={styles.managementToolbar}>
              <button
                type="button"
                className={styles.managementButton}
                onClick={onOpenAuth}
              >
                前往登录页
              </button>
            </div>
          </section>
        </div>
      </div>
    )
  }

  if (actor.role !== 'admin') {
    return (
      <div className={styles.managementPage}>
        <div className={styles.managementTopbar}>
          <div className={styles.managementRouteInfo}>
            <span className={styles.managementBreadcrumb}>账号 / 用户管理</span>
            <h2>用户管理</h2>
            <p>当前账号已登录，但该页面仅对管理员开放。</p>
          </div>
        </div>
        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>当前账号</h3>
              <span className={styles.accountRoleBadge}>普通用户</span>
            </div>
            <div className={styles.managementMetaPanel}>
              <span>邮箱: {actor.email || '-'}</span>
              <span>用户 ID: {actor.userId}</span>
            </div>
            <p className={styles.managementDescription}>
              你可以继续使用聊天、知识库和技能功能；用户账号管理仅管理员可见。
            </p>
          </section>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.managementPage}>
      <div className={styles.managementNoticeRow}>
        {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
        {error ? <div className={styles.managementError}>{error}</div> : null}
      </div>
      <div className={styles.managementTopbar}>
        <div className={styles.managementRouteInfo}>
          <span className={styles.managementBreadcrumb}>账号 / 用户管理</span>
          <h2>用户管理</h2>
          <p>管理员可创建账号、调整身份、启用或停用账号，并重置用户密码。</p>
        </div>
      </div>

      <div className={styles.managementPageGrid}>
        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>创建账号</h3>
            <span className={styles.accountRoleBadge}>管理员</span>
          </div>
          <div className={styles.managementForm}>
            <input
              className={styles.managementInput}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="新用户邮箱"
            />
            <input
              className={styles.managementInput}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="初始密码，至少 8 位"
            />
            <select
              className={styles.managementInput}
              value={role}
              onChange={(event) => setRole(event.target.value as 'admin' | 'user')}
            >
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
            <div className={styles.managementToolbar}>
              <button
                type="button"
                className={styles.managementButton}
                onClick={async () => {
                  await onCreateUser({ email, password, role })
                  setEmail('')
                  setPassword('')
                  setRole('user')
                }}
              >
                创建用户
              </button>
            </div>
          </div>
        </section>

        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>用户列表</h3>
            <span className={styles.managementMeta}>
              {loading ? '加载中...' : `共 ${users.length} 个账号`}
            </span>
          </div>
          <div className={styles.managementToolbar}>
            <div className={styles.managementSearchGroup}>
              <input
                className={styles.managementInput}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void onLoadUsers(search.trim())
                  }
                }}
                placeholder="按邮箱搜索"
              />
              <button
                type="button"
                className={styles.managementButton}
                onClick={() => void onLoadUsers(search.trim())}
              >
                搜索
              </button>
            </div>
          </div>

          <div className={styles.managementCardGrid}>
            {users.length === 0 ? (
              <div className={styles.managementEmpty}>当前没有匹配的用户。</div>
            ) : (
              users.map((user) => (
                <div key={user.user_id} className={styles.managementTileCard}>
                  <div className={styles.managementListHeader}>
                    <strong>{user.email}</strong>
                    <span className={styles.accountRoleBadge}>
                      {user.role === 'admin' ? '管理员' : '普通用户'}
                    </span>
                  </div>
                  <div className={styles.managementMetaPanel}>
                    <span>用户 ID: {user.user_id}</span>
                    <span>状态: {user.is_active ? '启用中' : '已停用'}</span>
                  </div>
                  <div className={styles.managementActionRow}>
                    <button
                      type="button"
                      className={styles.managementMinorButton}
                      onClick={() =>
                        void onUpdateUserRole(
                          user.user_id,
                          user.role === 'admin' ? 'user' : 'admin'
                        )
                      }
                    >
                      {user.role === 'admin' ? '设为普通用户' : '设为管理员'}
                    </button>
                    <button
                      type="button"
                      className={styles.managementMinorButton}
                      onClick={() => void onUpdateUserStatus(user.user_id, !user.is_active)}
                    >
                      {user.is_active ? '停用账号' : '启用账号'}
                    </button>
                    <button
                      type="button"
                      className={styles.managementDangerMinorButton}
                      onClick={() => {
                        const nextPassword = window.prompt(
                          `为 ${user.email} 设置新密码（至少 8 位）`
                        )
                        if (!nextPassword) return
                        void onResetUserPassword(user.user_id, nextPassword)
                      }}
                    >
                      重置密码
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
