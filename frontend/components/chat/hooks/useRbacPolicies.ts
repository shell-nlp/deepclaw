'use client'

import { useCallback, useState } from 'react'

import {
  RBAC_POLICIES_API_PATH,
  RBAC_POLICIES_CREATE_API_PATH,
  RBAC_POLICIES_DELETE_API_PATH,
  RBAC_ROLES_API_PATH,
  RBAC_ROLES_DELETE_API_PATH,
} from '../utils/constants'
import type {
  RbacPolicyItem,
  RbacPolicyListResponse,
  RbacRoleItem,
} from '../utils/types'

type RequestJson = <T>(path: string, init?: RequestInit) => Promise<T>

type UseRbacPoliciesInput = {
  requestJson: RequestJson
  canManage: boolean
}

type RbacPolicyDraft = {
  subject: string
  path: string
  action: string
}

type RbacRoleDraft = {
  child: string
  parent: string
}

const EMPTY_POLICY: RbacPolicyDraft = { subject: '', path: '', action: 'read' }
const EMPTY_ROLE: RbacRoleDraft = { child: '', parent: '' }

export function useRbacPolicies({ requestJson, canManage }: UseRbacPoliciesInput) {
  const [policies, setPolicies] = useState<RbacPolicyItem[]>([])
  const [roles, setRoles] = useState<RbacRoleItem[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [policyDraft, setPolicyDraft] = useState<RbacPolicyDraft>(EMPTY_POLICY)
  const [roleDraft, setRoleDraft] = useState<RbacRoleDraft>(EMPTY_ROLE)

  const applySnapshot = useCallback((snapshot: RbacPolicyListResponse) => {
    setPolicies(snapshot.policies)
    setRoles(snapshot.roles)
  }, [])

  const loadPolicies = useCallback(async () => {
    if (!canManage) {
      setPolicies([])
      setRoles([])
      return
    }
    setLoading(true)
    setError('')
    try {
      applySnapshot(await requestJson<RbacPolicyListResponse>(RBAC_POLICIES_API_PATH))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '加载授权策略失败。')
    } finally {
      setLoading(false)
    }
  }, [applySnapshot, canManage, requestJson])

  const runMutation = useCallback(
    async (
      path: string,
      body: Record<string, unknown>,
      successMessage: string,
      failureMessage: string
    ) => {
      setBusy(true)
      setNotice('')
      setError('')
      try {
        applySnapshot(
          await requestJson<RbacPolicyListResponse>(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
        )
        setNotice(successMessage)
        return true
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : failureMessage)
        return false
      } finally {
        setBusy(false)
      }
    },
    [applySnapshot, requestJson]
  )

  const createPolicy = useCallback(async () => {
    const subject = policyDraft.subject.trim()
    const path = policyDraft.path.trim()
    const action = policyDraft.action.trim()
    if (!subject || !path || !action) {
      setError('主体、路径和动作都不能为空。')
      return
    }
    const created = await runMutation(
      RBAC_POLICIES_CREATE_API_PATH,
      { subject, path, action },
      `已添加策略 ${subject} → ${path}（${action}）。`,
      '添加策略失败。'
    )
    if (created) setPolicyDraft({ ...EMPTY_POLICY, action })
  }, [policyDraft, runMutation])

  const deletePolicy = useCallback(
    async (policy: RbacPolicyItem) => {
      await runMutation(
        RBAC_POLICIES_DELETE_API_PATH,
        { subject: policy.subject, path: policy.path, action: policy.action },
        `已删除策略 ${policy.subject} → ${policy.path}（${policy.action}）。`,
        '删除策略失败。'
      )
    },
    [runMutation]
  )

  const createRole = useCallback(async () => {
    const child = roleDraft.child.trim()
    const parent = roleDraft.parent.trim()
    if (!child || !parent) {
      setError('子角色和父角色都不能为空。')
      return
    }
    const created = await runMutation(
      RBAC_ROLES_API_PATH,
      { child, parent },
      `已把 ${child} 加入 ${parent}。`,
      '添加角色关系失败。'
    )
    if (created) setRoleDraft(EMPTY_ROLE)
  }, [roleDraft, runMutation])

  const deleteRole = useCallback(
    async (role: RbacRoleItem) => {
      await runMutation(
        RBAC_ROLES_DELETE_API_PATH,
        { child: role.child, parent: role.parent },
        `已移除 ${role.child} 与 ${role.parent} 的关系。`,
        '删除角色关系失败。'
      )
    },
    [runMutation]
  )

  return {
    policies,
    roles,
    loading,
    busy,
    notice,
    error,
    policyDraft,
    roleDraft,
    setPolicyDraft,
    setRoleDraft,
    loadPolicies,
    createPolicy,
    deletePolicy,
    createRole,
    deleteRole,
  }
}
