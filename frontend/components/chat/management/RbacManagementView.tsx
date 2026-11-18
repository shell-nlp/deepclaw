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

  useEffect(() => {
    if (canManage) void onLoadPolicies()
  }, [canManage, onLoadPolicies])

  const visiblePolicies = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase()
    if (!keyword) return policies
    return policies.filter((policy) =>
      `${policy.subject} ${policy.path} ${policy.action}`
        .toLocaleLowerCase()
        .includes(keyword)
    )
  }, [policies, search])

  const subjectCount = useMemo(
    () => new Set(policies.map((policy) => policy.subject)).size,
    [policies]
  )

  if (!canManage) {
    return (
      <section className={styles.managementCard}>
        <div className={styles.managementHeader}>
          <h3>权限策略</h3>
          <span className={styles.accountRoleBadge}>仅管理员</span>
        </div>
        <p className={styles.managementDescription}>
          角色与权限策略由管理员维护。普通用户可以继续使用聊天、知识库和技能功能。
        </p>
      </section>
    )
  }

  return (
    <div className={styles.managementPageGrid}>
      {notice || error ? (
        <div className={styles.managementNoticeRow}>
          {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
          {error ? <div className={styles.managementError}>{error}</div> : null}
        </div>
      ) : null}

      <section className={styles.managementCard}>
        <div className={styles.managementHeader}>
          <h3>角色继承</h3>
          <span className={styles.managementMeta}>{roles.length} 条关系</span>
        </div>
        <p className={styles.managementDescription}>
          子角色继承父角色的全部策略；也可以把具体用户 ID 加入某个角色。
        </p>
        <div className={styles.managementDataList}>
          {roles.length === 0 ? (
            <div className={styles.managementEmpty}>当前没有角色继承关系。</div>
          ) : (
            roles.map((role) => (
              <div key={`${role.child}->${role.parent}`} className={styles.managementDataRow}>
                <span className={styles.managementDataPrimary}>
                  {role.child} <span aria-hidden="true">→</span> {role.parent}
                </span>
                <button
                  type="button"
                  className={styles.managementButton}
                  disabled={busy}
                  onClick={() => void onDeleteRole(role)}
                >
                  移除
                </button>
              </div>
            ))
          )}
        </div>
        <div className={styles.managementForm}>
          <input
            className={styles.managementInput}
            value={roleDraft.child}
            onChange={(event) =>
              onRoleDraftChange({ ...roleDraft, child: event.target.value })
            }
            placeholder="子角色或用户 ID"
          />
          <input
            className={styles.managementInput}
            value={roleDraft.parent}
            onChange={(event) =>
              onRoleDraftChange({ ...roleDraft, parent: event.target.value })
            }
            placeholder="父角色，例如 admin"
          />
          <div className={styles.managementToolbar}>
            <button
              type="button"
              className={styles.managementButton}
              disabled={busy}
              onClick={() => void onCreateRole()}
            >
              添加关系
            </button>
          </div>
        </div>
      </section>

      <section className={styles.managementCard}>
        <div className={styles.managementHeader}>
          <h3>权限策略</h3>
          <span className={styles.managementMeta}>
            {loading ? '加载中...' : `${policies.length} 条策略 / ${subjectCount} 个主体`}
          </span>
        </div>
        <p className={styles.managementDescription}>
          路径使用 Casbin keyMatch 规则，例如 <code>/api/rag/*</code> 匹配知识库全部接口。
          修改后立即生效，无需重启服务。
        </p>
        <div className={styles.managementToolbar}>
          <div className={styles.managementSearchGroup}>
            <input
              className={styles.managementInput}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="按主体、路径或动作筛选"
            />
            <button
              type="button"
              className={styles.managementButton}
              disabled={loading}
              onClick={() => void onLoadPolicies()}
            >
              刷新
            </button>
          </div>
        </div>
        <div className={styles.managementDataList}>
          {visiblePolicies.length === 0 ? (
            <div className={styles.managementEmpty}>当前没有匹配的策略。</div>
          ) : (
            visiblePolicies.map((policy) => (
              <div
                key={`${policy.subject}|${policy.path}|${policy.action}`}
                className={styles.managementDataRow}
              >
                <span className={styles.managementDataPrimary}>{policy.subject}</span>
                <span className={styles.managementMeta}>{policy.path}</span>
                <span className={styles.managementMeta}>{policy.action}</span>
                <button
                  type="button"
                  className={styles.managementButton}
                  disabled={busy}
                  onClick={() => void onDeletePolicy(policy)}
                >
                  删除
                </button>
              </div>
            ))
          )}
        </div>
        <div className={styles.managementForm}>
          <input
            className={styles.managementInput}
            value={policyDraft.subject}
            onChange={(event) =>
              onPolicyDraftChange({ ...policyDraft, subject: event.target.value })
            }
            placeholder="主体，例如 user / admin / 用户 ID"
          />
          <input
            className={styles.managementInput}
            value={policyDraft.path}
            onChange={(event) =>
              onPolicyDraftChange({ ...policyDraft, path: event.target.value })
            }
            placeholder="资源路径，例如 /api/rag/*"
          />
          <select
            className={styles.managementInput}
            value={policyDraft.action}
            onChange={(event) =>
              onPolicyDraftChange({ ...policyDraft, action: event.target.value })
            }
          >
            <option value="read">read</option>
            <option value="write">write</option>
          </select>
          <div className={styles.managementToolbar}>
            <button
              type="button"
              className={styles.managementButton}
              disabled={busy}
              onClick={() => void onCreatePolicy()}
            >
              添加策略
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
