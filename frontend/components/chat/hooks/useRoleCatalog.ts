'use client'

import { useCallback, useEffect, useState } from 'react'
import { RBAC_ROLE_CATALOG_API_PATH } from '../utils/constants'
import type { RoleCatalogRecord, RoleCatalogResponse } from '../utils/types'

type RequestJson = <T>(path: string, init?: RequestInit) => Promise<T>

/** 管理持久化角色清单和整组权限的提交。
 * Args:
 *   requestJson: 带身份验证的 API 请求函数。
 *   canManage: 当前用户是否能维护角色。
 */
export function useRoleCatalog(requestJson: RequestJson, canManage: boolean) {
  const [roles, setRoles] = useState<RoleCatalogRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const loadRoles = useCallback(async () => {
    if (!canManage) { setRoles([]); return }
    setLoading(true)
    setError('')
    try {
      const response = await requestJson<RoleCatalogResponse>(RBAC_ROLE_CATALOG_API_PATH)
      setRoles(response.roles)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '读取角色失败。')
    } finally {
      setLoading(false)
    }
  }, [canManage, requestJson])

  useEffect(() => { void loadRoles() }, [loadRoles])

  const mutate = useCallback(async (
    path: string,
    method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
    input: Record<string, unknown> | null,
    message: string,
  ): Promise<boolean> => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await requestJson<unknown>(path, {
        method,
        headers: input ? { 'Content-Type': 'application/json' } : undefined,
        body: input ? JSON.stringify(input) : undefined,
      })
      await loadRoles()
      setNotice(message)
      return true
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '角色操作失败。')
      return false
    } finally {
      setBusy(false)
    }
  }, [loadRoles, requestJson])

  const createRole = useCallback((input: { id: string; name: string; description: string }) =>
    mutate(RBAC_ROLE_CATALOG_API_PATH, 'POST', input, '角色已创建，请在右侧为它配置权限。'), [mutate])

  const saveRole = useCallback((id: string, input: { name: string; description: string }) =>
    mutate(RBAC_ROLE_CATALOG_API_PATH + '/' + encodeURIComponent(id), 'PATCH', input, '角色信息已保存。'), [mutate])

  const savePermissions = useCallback((id: string, permissions: Array<{ path: string; action: string }>) =>
    mutate(RBAC_ROLE_CATALOG_API_PATH + '/' + encodeURIComponent(id) + '/permissions', 'PUT', { permissions }, '角色权限已保存。'), [mutate])

  const deleteRole = useCallback((id: string) =>
    mutate(RBAC_ROLE_CATALOG_API_PATH + '/' + encodeURIComponent(id), 'DELETE', null, '角色已删除。'), [mutate])

  return { roles, loading, busy, notice, error, loadRoles, createRole, saveRole, savePermissions, deleteRole }
}
