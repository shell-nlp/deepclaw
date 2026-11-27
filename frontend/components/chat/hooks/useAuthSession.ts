'use client'

import { useCallback, useRef, useState } from 'react'

import {
  buildAuthorizationHeaders,
  clearStoredAuthToken,
  fetchAuthRuntimeConfig,
  getActorCapabilities,
  getStoredAuthToken,
  GUEST_USER_ID,
  isUnauthorizedError,
  normalizeActorPayload,
  redirectToLogin,
  revokeAuthToken,
  type ActorState,
} from '../utils/auth'
import {
  AUTH_USERS_CREATE_API_PATH,
  AUTH_USERS_LIST_API_PATH,
  AUTH_USERS_RESET_PASSWORD_API_PATH,
  AUTH_USERS_UPDATE_PROFILE_API_PATH,
  AUTH_USERS_DELETE_API_PATH,
  AUTH_USERS_UPDATE_ROLE_API_PATH,
  AUTH_USERS_UPDATE_STATUS_API_PATH,
} from '../utils/constants'
import { fetchJson, getApiUrl } from '../utils'
import type {
  AuthLoginResponse,
  AuthUserListResponse,
  AuthUserSummary,
} from '../utils/types'

type UseAuthSessionOptions = {
  onActorChange: () => void
  setManagementNotice: (notice: string) => void
}

/**
 * 管理登录身份、认证头、接口请求与管理员用户操作。
 *
 * Args:
 *   options: 身份切换回调与全局提示写入函数。
 */
export function useAuthSession({
  onActorChange,
  setManagementNotice,
}: UseAuthSessionOptions) {
  const [actor, setActor] = useState<ActorState>(() => normalizeActorPayload(null))
  const [authToken, setAuthToken] = useState('')
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const [adminUsers, setAdminUsers] = useState<AuthUserSummary[]>([])
  const [loadingAdminUsers, setLoadingAdminUsers] = useState(false)
  const [userAdminNotice, setUserAdminNotice] = useState('')
  const [userAdminError, setUserAdminError] = useState('')

  const actorCapabilities = getActorCapabilities(actor)
  const currentUserId = actor.userId || GUEST_USER_ID
  const onActorChangeRef = useRef(onActorChange)
  onActorChangeRef.current = onActorChange

  const applyActorState = useCallback((nextActor: ActorState) => {
    setActor(nextActor)
    onActorChangeRef.current()
  }, [])

  const clearAuthState = useCallback(
    (notice = '已切换为游客模式。') => {
      clearStoredAuthToken()
      setAuthToken('')
      applyActorState(normalizeActorPayload(null))
      setAccountMenuOpen(false)
      setUserAdminNotice('')
      setUserAdminError('')
      setManagementNotice(notice)
    },
    [applyActorState, setManagementNotice]
  )

  const withAuthHeaders = useCallback(
    (headers?: HeadersInit) => {
      // 首次挂载时 authToken state 尚未由 effect 写入，回退本地存储避免请求漏带令牌触发 401
      const effectiveToken =
        authToken || (typeof window === 'undefined' ? '' : getStoredAuthToken())
      return {
        ...(headers || {}),
        ...buildAuthorizationHeaders(effectiveToken),
      }
    },
    [authToken]
  )

  const requestJson = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      try {
        return await fetchJson<T>(getApiUrl(path), {
          ...init,
          headers: withAuthHeaders(init?.headers),
        })
      } catch (error) {
        if (isUnauthorizedError(error)) {
          const { allowGuest } = await fetchAuthRuntimeConfig()
          if (allowGuest) {
            clearAuthState('登录状态已失效，已切换为游客模式。')
          } else {
            clearAuthState('登录状态已失效，请重新登录。')
            redirectToLogin()
          }
        }
        throw error
      }
    },
    [clearAuthState, withAuthHeaders]
  )

  const loadAdminUsers = useCallback(
    async (search = '') => {
      if (actor.isGuest || !actorCapabilities.canManageUsers) {
        setAdminUsers([])
        return
      }
      setLoadingAdminUsers(true)
      setUserAdminError('')
      try {
        const result = await requestJson<AuthUserListResponse>(AUTH_USERS_LIST_API_PATH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ search }),
        })
        setAdminUsers(result.items)
      } catch (error) {
        setUserAdminError(error instanceof Error ? error.message : '加载用户列表失败。')
      } finally {
        setLoadingAdminUsers(false)
      }
    },
    [actor.isGuest, actorCapabilities.canManageUsers, requestJson]
  )

  const handleLogout = async () => {
    try {
      if (authToken) {
        await revokeAuthToken(authToken)
      }
    } catch {
      // ignore logout failure
    } finally {
      clearAuthState('已退出登录，当前为游客模式。')
      setAccountMenuOpen(false)
    }
  }

  const openLoginPage = useCallback(() => {
    if (typeof window === 'undefined') return
    const next = `${window.location.pathname}${window.location.hash || '#/chat'}`
    window.location.assign(`/login?next=${encodeURIComponent(next)}`)
  }, [])

  const createAdminUser = async (input: {
    username: string
    password: string
    role: string
    display_name?: string
  }) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      await requestJson<AuthLoginResponse>(AUTH_USERS_CREATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      })
      await loadAdminUsers()
      setUserAdminNotice(`已创建账号 ${input.username}。`)
      return true
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '创建用户失败。')
      return false
    }
  }

  const updateAdminUserRole = async (userId: string, role: string) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      await requestJson<AuthLoginResponse>(AUTH_USERS_UPDATE_ROLE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, role }),
      })
      await loadAdminUsers()
      setUserAdminNotice('用户角色已更新。')
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '更新用户角色失败。')
    }
  }

  const updateAdminUserStatus = async (userId: string, isActive: boolean) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      await requestJson<AuthLoginResponse>(AUTH_USERS_UPDATE_STATUS_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, is_active: isActive }),
      })
      await loadAdminUsers()
      setUserAdminNotice(isActive ? '用户账号已启用。' : '用户账号已停用。')
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '更新用户状态失败。')
    }
  }

  const updateAdminUserProfile = async (
    userId: string,
    input: { username?: string; email?: string; display_name?: string }
  ) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      const { user } = await requestJson<AuthLoginResponse>(AUTH_USERS_UPDATE_PROFILE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          username: input.username ?? null,
          email: input.email ?? null,
          display_name: input.display_name,
        }),
      })
      await loadAdminUsers()
      setActor((previous) => previous.userId === user.user_id ? {
        ...previous,
        username: user.username ?? null,
        displayName: user.display_name ?? null,
        email: user.email ?? null,
      } : previous)
      setUserAdminNotice('用户资料已更新。')
      return true
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '更新用户资料失败。')
      return false
    }
  }

  const deleteAdminUser = async (userId: string) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      await requestJson<{ deleted: boolean }>(AUTH_USERS_DELETE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
      await loadAdminUsers()
      setUserAdminNotice('用户已删除。')
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '删除用户失败。')
    }
  }

  const resetAdminUserPassword = async (userId: string, password: string) => {
    setUserAdminNotice('')
    setUserAdminError('')
    try {
      await requestJson<AuthLoginResponse>(AUTH_USERS_RESET_PASSWORD_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, password }),
      })
      setUserAdminNotice('用户密码已重置。')
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '重置密码失败。')
    }
  }

  return {
    actor,
    setActor,
    authToken,
    setAuthToken,
    accountMenuOpen,
    setAccountMenuOpen,
    adminUsers,
    setAdminUsers,
    loadingAdminUsers,
    userAdminNotice,
    userAdminError,
    actorCapabilities,
    currentUserId,
    applyActorState,
    clearAuthState,
    withAuthHeaders,
    requestJson,
    loadAdminUsers,
    handleLogout,
    openLoginPage,
    createAdminUser,
    updateAdminUserRole,
    updateAdminUserStatus,
    updateAdminUserProfile,
    deleteAdminUser,
    resetAdminUserPassword,
  }
}
