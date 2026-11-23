'use client'

import { useMemo, useState } from 'react'
import styles from './RbacManagementView.module.css'
import type { PermissionDefinition, RoleCatalogRecord } from '../utils/types'

interface RbacManagementViewProps {
  canView: boolean
  canManage: boolean
  catalog: RoleCatalogRecord[]
  permissionDefinitions: PermissionDefinition[]
  loading: boolean
  busy: boolean
  notice: string
  error: string
  onCreateRole: (input: { id: string; name: string; description: string }) => Promise<boolean>
  onSaveRole: (id: string, input: { name: string; description: string }) => Promise<boolean>
  onDeleteRole: (id: string) => Promise<boolean>
  onSavePermissions: (id: string, permissions: Array<{ path: string; action: string }>) => Promise<boolean>
}

function pairKey(path: string, action: string): string {
  return path + ':' + action
}

/** 按角色清单与服务端模块权限目录维护授权。
 * Args:
 *   props: 角色数据、权限定义、管理能力和操作回调。
 */
export function RbacManagementView({
  canView,
  canManage,
  catalog,
  permissionDefinitions,
  loading,
  busy,
  notice,
  error,
  onCreateRole,
  onSaveRole,
  onDeleteRole,
  onSavePermissions,
}: RbacManagementViewProps) {
  const [selectedId, setSelectedId] = useState('')
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')
  const [draftPermissionCodes, setDraftPermissionCodes] = useState<string[]>([])
  const [draftInitializedFor, setDraftInitializedFor] = useState('')
  const [expandedGroups, setExpandedGroups] = useState<string[]>([])

  const selected = useMemo(
    () => catalog.find((role) => role.id === selectedId) ?? catalog[0] ?? null,
    [catalog, selectedId]
  )
  const groups = useMemo(
    () => Array.from(new Set(permissionDefinitions.map((permission) => permission.group))),
    [permissionDefinitions]
  )
  const permissionGroups = groups
  const knownPairs = useMemo(
    () => new Set(permissionDefinitions.flatMap((permission) => permission.rules.map((rule) => pairKey(rule.path, rule.action)))),
    [permissionDefinitions]
  )
  const selectedPairs = useMemo(
    () => new Set((selected?.permissions ?? []).map((permission) => pairKey(permission.path, permission.action))),
    [selected]
  )
  const draftForSelected = selected !== null && draftInitializedFor === selected.id
  const enabledCodes = draftForSelected
    ? draftPermissionCodes
    : permissionDefinitions.filter((permission) => permission.rules.every((rule) => selectedPairs.has(pairKey(rule.path, rule.action)))).map((permission) => permission.code)
  const visibleUnknownRules = (selected?.permissions ?? []).filter((permission) => !knownPairs.has(pairKey(permission.path, permission.action)))
  const unknownPolicies = visibleUnknownRules
  const dirty = Boolean(selected && !selected.builtin && draftForSelected && (
    draftName !== selected.name || draftDescription !== selected.description ||
    JSON.stringify([...draftPermissionCodes].sort()) !== JSON.stringify(permissionDefinitions.filter((permission) => permission.rules.every((rule) => selectedPairs.has(pairKey(rule.path, rule.action)))).map((permission) => permission.code).sort())
  ))

  /** 选择角色并为该角色初始化本地编辑草稿。
   * Args:
   *   role: 被选中的角色。
   */
  const selectRole = (role: RoleCatalogRecord) => {
    setSelectedId(role.id)
    setDraftName(role.name)
    setDraftDescription(role.description)
    setDraftPermissionCodes(permissionDefinitions.filter((permission) => permission.rules.every((rule) => role.permissions.some((item) => item.path === rule.path && item.action === rule.action))).map((permission) => permission.code))
    setDraftInitializedFor(role.id)
  }

  /** 为自定义角色切换一个服务端定义的功能权限。
   * Args:
   *   code: 权限目录中的稳定权限代码。
   */
  const togglePermission = (code: string) => {
    if (!selected || selected.builtin || !canManage) return
    if (!draftForSelected) selectRole(selected)
    const current = draftForSelected ? draftPermissionCodes : enabledCodes
    setDraftPermissionCodes(current.includes(code) ? current.filter((item) => item !== code) : [...current, code])
    setDraftInitializedFor(selected.id)
  }

  /** 新建角色并自动选中，显示名可使用中文。
   * Args:
   *   无。
   */
  const createRole = async () => {
    const name = newName.trim()
    if (!name) return
    const id = 'role_' + crypto.randomUUID().replace(/-/g, '')
    if (await onCreateRole({ id, name, description: newDescription.trim() })) {
      setNewName('')
      setNewDescription('')
      const created: RoleCatalogRecord = { id, name, description: newDescription.trim(), builtin: false, user_count: 0, permissions: [] }
      selectRole(created)
    }
  }

  /** 保存名称、说明和模块权限目录映射的 Casbin 规则。
   * Args:
   *   无。
   */
  const saveRole = async () => {
    if (!selected || selected.builtin || !canManage || !dirty) return
    if (draftName.trim() !== selected.name || draftDescription.trim() !== selected.description) {
      const saved = await onSaveRole(selected.id, { name: draftName.trim(), description: draftDescription.trim() })
      if (!saved) return
    }
    const rules: Array<{ path: string; action: string }> = permissionDefinitions
      .filter((permission) => enabledCodes.includes(permission.code))
      .flatMap((permission) => permission.rules.map(({ path, action }) => ({ path, action })))
    rules.push(...visibleUnknownRules)
    if (await onSavePermissions(selected.id, rules)) {
      setDraftInitializedFor('')
    }
  }

  /** 删除未分配给任何账号的自定义角色。
   * Args:
   *   无。
   */
  const deleteRole = async () => {
    if (!selected || selected.builtin || !canManage || selected.user_count > 0) return
    if (!window.confirm('删除角色「' + selected.name + '」？')) return
    if (await onDeleteRole(selected.id)) {
      setSelectedId('')
      setDraftInitializedFor('')
    }
  }

  if (!canView && !canManage) {
    return <div className={styles.page}><header className={styles.header}><div><span className={styles.breadcrumb}>系统 / 角色管理</span><h2>角色管理</h2></div></header><p className={styles.empty}>当前账号没有查看角色的权限。</p></div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div><span className={styles.breadcrumb}>系统 / 角色管理</span><h2>角色管理</h2><p>选择角色，按业务模块勾选权限；保存后用户立即按新权限访问。</p></div>
        <span className={styles.counter}>{catalog.length} 个角色</span>
      </header>
      {notice && <p role="status" className={styles.notice}>{notice}</p>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div className={styles.columns}>
        <section className={styles.panel} aria-label="角色清单">
          <div className={styles.panelTitle}><h3>角色清单</h3><span>{catalog.length} 个</span></div>
          {loading && !catalog.length ? <p className={styles.empty}>正在读取角色…</p> : (
            <div className={styles.roleList}>
              {catalog.map((role) => (
                <button type="button" key={role.id} className={styles.roleRow + (selected?.id === role.id ? ' ' + styles.selected : '')} onClick={() => selectRole(role)} aria-pressed={selected?.id === role.id}>
                  <span className={styles.roleMark} aria-hidden="true" />
                  <span className={styles.roleIdentity}><strong>{role.name}</strong><small>{role.user_count} 个账号在用{role.builtin ? ' · 内置角色' : ''}</small></span>
                </button>
              ))}
              {!catalog.length && <p className={styles.empty}>还没有角色。先新建一个。</p>}
            </div>
          )}
          {canManage && <form className={styles.createForm} onSubmit={(event) => { event.preventDefault(); void createRole() }}>
            <strong>新建角色</strong>
            <label>角色名称<input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="例如：知识库编辑者" disabled={busy} /></label>
            <label>用途说明<input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} placeholder="这个角色给谁使用" disabled={busy} /></label>
            <button type="submit" disabled={busy || !newName.trim()} className={styles.primary}>新建角色</button>
          </form>}
        </section>
        <section className={styles.panel} aria-label="角色权限">
          {!selected ? <div className={styles.empty}>请先从左边选择角色。</div> : <>
            <div className={styles.detailHeader}>
              <div><small>角色权限</small><h3>{selected.name}</h3><p>{selected.description || (selected.user_count + ' 个账号使用此角色')}</p></div>
              {selected.builtin ? <span className={styles.builtin}>内置角色 · 只读</span> : canManage ? <div className={styles.actions}><button type="button" className={styles.primary} onClick={() => void saveRole()} disabled={busy || !dirty || !draftName.trim()}>保存修改</button><button type="button" className={styles.danger} onClick={() => void deleteRole()} disabled={busy || selected.user_count > 0}>删除角色</button></div> : <span className={styles.builtin}>只读</span>}
            </div>
            {selected.builtin && <p className={styles.note}>这是平台内置角色，权限由平台维护，不可修改。需要不同权限时，请新建自定义角色。</p>}
            {!selected.builtin && canManage && <div className={styles.identityFields}>
              <label>角色名称<input value={draftForSelected ? draftName : selected.name} onChange={(event) => { if (!draftForSelected) selectRole(selected); setDraftName(event.target.value); setDraftInitializedFor(selected.id) }} disabled={busy} /></label>
              <label>用途说明<input value={draftForSelected ? draftDescription : selected.description} onChange={(event) => { if (!draftForSelected) selectRole(selected); setDraftDescription(event.target.value); setDraftInitializedFor(selected.id) }} disabled={busy} /></label>
            </div>}
            <div className={styles.matrix}>
              {permissionGroups.map((group) => {
                const permissions = permissionDefinitions.filter((item) => item.group === group)
                const enabledCount = permissions.filter((item) => enabledCodes.includes(item.code)).length
                const expanded = expandedGroups.includes(group)
                return <section className={styles.permissionGroup} key={group}>
                  <button type="button" className={styles.groupHeader} aria-expanded={expanded} onClick={() => setExpandedGroups((current) => current.includes(group) ? current.filter((item) => item !== group) : [...current, group])}>
                    <span><strong>{group}</strong><small>{permissions.length} 项功能</small></span>
                    <span>{enabledCount} / {permissions.length} 已授权 <b>{expanded ? '⌃' : '⌄'}</b></span>
                  </button>
                  {expanded && <div className={styles.groupPermissions}>{permissions.map((permission) => {
                    const checked = enabledCodes.includes(permission.code)
                    return <label className={styles.permissionRow + (checked ? ' ' + styles.granted : '')} key={permission.code}>
                      <input type="checkbox" checked={checked} disabled={busy || selected.builtin || !canManage} onChange={() => togglePermission(permission.code)} />
                      <span className={styles.permissionText}><strong>{permission.name}</strong><small>{permission.description}</small>{permission.rules.map((rule) => <code key={rule.path + rule.action} title="对应的服务端路由">{rule.path} · {rule.action}</code>)}</span>
                    </label>
                  })}</div>}
                </section>
              })}
            </div>
            {unknownPolicies.length > 0 && <p className={styles.note}>还有 {unknownPolicies.length} 条未归类的旧规则。编辑角色时会保留，暂不出现在权限矩阵。</p>}
            {!selected.builtin && canManage && <div className={styles.footer}><span>{draftForSelected && dirty ? '有未保存的权限变更' : '勾选权限后点击“保存修改”使变更生效'}</span><button type="button" className={styles.primary} onClick={() => void saveRole()} disabled={busy || !dirty || !draftName.trim()}>保存修改</button></div>}
          </>}
        </section>
      </div>
    </div>
  )
}
