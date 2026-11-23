'use client'

import { useMemo, useState } from 'react'
import styles from './RbacManagementView.module.css'
import type { RoleCatalogRecord } from '../utils/types'
import { PERMISSION_CHOICES, permissionKey } from './rolePermissions'

interface RbacManagementViewProps {
  canManage: boolean
  catalog: RoleCatalogRecord[]
  loading: boolean
  busy: boolean
  notice: string
  error: string
  onCreateRole: (input: { id: string; name: string; description: string }) => Promise<boolean>
  onSaveRole: (id: string, input: { name: string; description: string }) => Promise<boolean>
  onDeleteRole: (id: string) => Promise<boolean>
  onSavePermissions: (id: string, permissions: Array<{ path: string; action: string }>) => Promise<boolean>
}

const PERMISSION_GROUPS = Array.from(new Set(PERMISSION_CHOICES.map((item) => item.group)))

/** 角色管理工作区：左选角色，右侧按实际功能点勾选权限。
 * Args:
 *   props: 角色目录、操作状态及由鉴权 Hook 提供的操作回调。
 */
export function RbacManagementView({
  canManage, catalog, loading, busy, notice, error,
  onCreateRole, onSaveRole, onDeleteRole, onSavePermissions,
}: RbacManagementViewProps) {
  const [selectedId, setSelectedId] = useState('')
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')
  const [draftPermissions, setDraftPermissions] = useState<string[]>([])
  const [touched, setTouched] = useState(false)

  const selected = useMemo(
    () => catalog.find((item) => item.id === selectedId) ?? catalog[0] ?? null,
    [catalog, selectedId]
  )
  const selectedKeys = useMemo(
    () => (selected?.permissions || []).map((item) => permissionKey(item.path, item.action)),
    [selected]
  )
  const effectiveKeys = touched ? draftPermissions : selectedKeys
  const effectiveName = touched ? draftName : selected?.name || ''
  const effectiveDescription = touched ? draftDescription : selected?.description || ''
  const knownKeys = new Set(PERMISSION_CHOICES.map((item) => permissionKey(item.path, item.action)))
  const unknownPolicies = (selected?.permissions || []).filter(
    (item) => !knownKeys.has(permissionKey(item.path, item.action))
  )

  /** 切换所选角色并废弃上一个角色未保存的草稿。
   * Args:
   *   role: 被选中的角色。
   */
  const selectRole = (role: RoleCatalogRecord) => {
    setSelectedId(role.id)
    setDraftName(role.name)
    setDraftDescription(role.description)
    setDraftPermissions(role.permissions.map((item) => permissionKey(item.path, item.action)))
    setTouched(false)
  }

  /** 切换一个权限点的选中状态。
   * Args:
   *   key: 路径与动作的稳定组合键。
   */
  const toggle = (key: string) => {
    if (!selected || selected.builtin) return
    if (!touched) {
      setDraftName(selected.name)
      setDraftDescription(selected.description)
    }
    setDraftPermissions((current) => {
      const source = touched ? current : selectedKeys
      return source.includes(key) ? source.filter((item) => item !== key) : [...source, key]
    })
    setTouched(true)
  }

  /** 新建角色并选中它；角色内部标识自动生成，显示名可用中文。
   * Args:
   *   无。
   */
  const create = async () => {
    const id = 'role_' + crypto.randomUUID().replace(/-/g, '')
    if (await onCreateRole({ id, name: newName.trim(), description: newDescription.trim() })) {
      const name = newName.trim()
      const description = newDescription.trim()
      setNewName('')
      setNewDescription('')
      selectRole({ id, name, description, builtin: false, user_count: 0, permissions: [] })
    }
  }

  /** 保存角色名称和权限快照；失败时保持草稿以便重试。
   * Args:
   *   无。
   */
  const save = async () => {
    if (!selected || selected.builtin || !effectiveName.trim()) return
    const roleChanged = effectiveName !== selected.name || effectiveDescription !== selected.description
    if (roleChanged && !await onSaveRole(selected.id, { name: effectiveName.trim(), description: effectiveDescription.trim() })) return
    const permissions: Array<{ path: string; action: string }> = PERMISSION_CHOICES
      .filter((item) => effectiveKeys.includes(permissionKey(item.path, item.action)))
      .map(({ path, action }) => ({ path, action }))
    permissions.push(...unknownPolicies)
    if (await onSavePermissions(selected.id, permissions)) setTouched(false)
  }

  /** 删除未被账号使用的自定义角色。
   * Args:
   *   无。
   */
  const remove = async () => {
    if (!selected || selected.builtin || !window.confirm('删除角色「' + selected.name + '」？')) return
    if (await onDeleteRole(selected.id)) {
      setSelectedId('')
      setTouched(false)
    }
  }

  if (!canManage) return (
    <div className={styles.page}>
      <header className={styles.header}><div><span className={styles.breadcrumb}>系统 / 角色管理</span><h2>角色管理</h2></div></header>
      <p className={styles.empty}>仅有角色管理权限的账号可以查看和配置角色。</p>
    </div>
  )

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div><span className={styles.breadcrumb}>系统 / 角色管理</span><h2>角色管理</h2><p>先选角色，再勾选它能使用的功能，最后保存。</p></div>
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
                <button type="button" key={role.id} className={styles.roleRow + (selected?.id === role.id ? ' ' + styles.selected : '')}
                  onClick={() => selectRole(role)} aria-pressed={selected?.id === role.id}>
                  <span className={styles.roleMark} aria-hidden="true" />
                  <span className={styles.roleIdentity}><strong>{role.name}</strong><small>{role.user_count} 个账号在用{role.builtin ? ' · 内置' : ''}</small></span>
                </button>
              ))}
              {!catalog.length && <p className={styles.empty}>还没有角色。先新建一个。</p>}
            </div>
          )}
          <form className={styles.createForm} onSubmit={(event) => { event.preventDefault(); void create() }}>
            <strong>新建角色</strong>
            <label>角色名称<input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="例如：知识库编辑者" disabled={busy} /></label>
            <label>用途说明<input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} placeholder="这个角色给谁使用" disabled={busy} /></label>
            <button type="submit" disabled={busy || !newName.trim()} className={styles.primary}>新建角色</button>
          </form>
        </section>
        <section className={styles.panel} aria-label="角色权限">
          {!selected ? <div className={styles.empty}>请先从左边选择角色。</div> : (
            <>
              <div className={styles.detailHeader}>
                <div><small>权限配置</small><h3>{selected.name}</h3><p>{selected.user_count} 个账号使用此角色</p></div>
                {selected.builtin ? <span className={styles.builtin}>内置角色 · 只读</span> : (
                  <div className={styles.actions}>
                    <button type="button" className={styles.primary} onClick={() => void save()} disabled={busy || !effectiveName.trim()}>保存角色</button>
                    <button type="button" className={styles.danger} onClick={() => void remove()} disabled={busy || selected.user_count > 0}>删除角色</button>
                  </div>
                )}
              </div>
              {selected.builtin ? <p className={styles.note}>内置角色不能修改。可以新建一个角色，为它单独配置功能权限。</p> : (
                <div className={styles.identityFields}>
                  <label>角色名称<input value={effectiveName} onChange={(event) => { if (!touched) { setDraftDescription(selected.description); setDraftPermissions(selectedKeys) }; setDraftName(event.target.value); setTouched(true) }} disabled={busy} /></label>
                  <label>用途说明<input value={effectiveDescription} onChange={(event) => { if (!touched) { setDraftName(selected.name); setDraftPermissions(selectedKeys) }; setDraftDescription(event.target.value); setTouched(true) }} disabled={busy} /></label>
                </div>
              )}
              <div className={styles.matrix}>
                {PERMISSION_GROUPS.map((group) => {
                  const specs = PERMISSION_CHOICES.filter((item) => item.group === group)
                  const activeCount = specs.filter((item) => effectiveKeys.includes(permissionKey(item.path, item.action))).length
                  return <section className={styles.permissionGroup} key={group}>
                    <div className={styles.groupHeader}><h4>{group}</h4><span>{activeCount} / {specs.length}</span></div>
                    {specs.map((item) => {
                      const checked = effectiveKeys.includes(permissionKey(item.path, item.action))
                      return <label className={styles.permissionRow + (checked ? ' ' + styles.granted : '')} key={permissionKey(item.path, item.action)}>
                        <input type="checkbox" checked={checked} disabled={busy || selected.builtin} onChange={() => toggle(permissionKey(item.path, item.action))} />
                        <span className={styles.permissionText}><strong>{item.label}</strong><small>{item.detail}</small><code title="对应资源路径">{item.path} · {item.action}</code></span>
                      </label>
                    })}
                  </section>
                })}
              </div>
              {unknownPolicies.length > 0 && <p className={styles.note}>另有 {unknownPolicies.length} 条旧策略不在常用功能列表中；保存角色时会保留它们。</p>}
              {!selected.builtin && <div className={styles.footer}><span>{touched ? '有未保存的修改' : '修改后保存才会生效'}</span><button type="button" className={styles.primary} onClick={() => void save()} disabled={busy || !effectiveName.trim()}>保存角色</button></div>}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
