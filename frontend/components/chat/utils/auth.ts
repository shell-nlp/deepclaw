import {
  AUTH_CONFIG_API_PATH,
  AUTH_LOGIN_API_PATH,
  AUTH_LOGOUT_API_PATH,
  AUTH_ME_API_PATH,
  AUTH_REGISTER_API_PATH,
  AUTH_REMEMBER_LOGIN_STORAGE_KEY,
  AUTH_TOKEN_STORAGE_KEY,
} from './constants.ts'
import type { AuthLoginResponse, AuthUserSummary } from './types.ts'
import { fetchJson, getApiUrl } from './index.ts'

export const GUEST_USER_ID = 'guest'

export type ActorRole = string
export interface ActorPermission { path: string; action: string }

export interface ActorState {
  isGuest: boolean
  userId: string
  username: string | null
  email: string | null
  role: ActorRole
  permissions?: ActorPermission[]
}

export interface ActorPayload {
  is_guest?: boolean
  user_id?: string | null
  username?: string | null
  email?: string | null
  role?: string | null
  permissions?: ActorPermission[]
}

export interface ActorCapabilities {
  canViewChat: boolean
  canUseChat: boolean
  canViewSchedules: boolean
  canManageSchedules: boolean
  canUseMcp: boolean
  canViewKnowledge: boolean
  canManageKnowledge: boolean
  canManageSkills: boolean
  canManageUsers: boolean
  canViewRoles: boolean
  canManageRoles: boolean
  canViewModels: boolean
  canManageModels: boolean
  canManageChannelBindingsGlobally: boolean
  requiresLoginMessage: string
}

export interface RememberedLogin {
  username: string
  password: string
}

export function buildAuthorizationHeaders(token: string | null | undefined): HeadersInit {
  const normalized = token?.trim()
  if (!normalized) {
    return {}
  }
  return {
    Authorization: `Bearer ${normalized}`,
  }
}

export function normalizeActorPayload(payload: ActorPayload | null | undefined): ActorState {
  if (!payload || payload.is_guest !== false || !payload.user_id) {
    return {
      isGuest: true,
      userId: GUEST_USER_ID,
      username: null,
      email: null,
      role: 'guest',
      permissions: [],
    }
  }

  const role = payload.role?.trim() || 'user'
  const actor: ActorState = {
    isGuest: false,
    userId: payload.user_id,
    username: payload.username ?? null,
    email: payload.email ?? null,
    role,
  }
  if (Array.isArray(payload.permissions)) {
    actor.permissions = payload.permissions
  }
  return actor
}

export function normalizeUserToActor(user: AuthUserSummary): ActorState {
  return normalizeActorPayload({
    is_guest: false,
    user_id: user.user_id,
    username: user.username,
    email: user.email,
    role: user.role,
    permissions: user.permissions,
  })
}

export function getActorCapabilities(actor: ActorState): ActorCapabilities {
  const grants = actor.permissions
  const allowed = (path: string, action: string) => actor.role === 'admin' || Boolean(grants?.some((item) => {
    if (item.action !== action) return false
    return item.path === path || (item.path.endsWith('/*') && path.startsWith(item.path.slice(0, -1)))
  }))
  const hasPermissions = Boolean(grants)
  return {
    canViewChat: actor.isGuest || allowed('/api/agui/threads', 'read'),
    canUseChat: actor.isGuest || (allowed('/api/agui/runs', 'read') && allowed('/api/agui/runs', 'write')),
    canViewSchedules: allowed('/api/schedules', 'read'),
    canManageSchedules: allowed('/api/schedules', 'write'),
    canUseMcp: allowed('/agent/tools/mcp', 'use'),
    canViewKnowledge: actor.isGuest || !hasPermissions || allowed('/api/rag/knowledge-bases/list', 'read'),
    canManageKnowledge: actor.isGuest || !hasPermissions || allowed('/api/rag/knowledge-bases/list', 'write'),
    canManageSkills: actor.isGuest || !hasPermissions || allowed('/api/agent/skills/list', 'write'),
    canManageUsers: allowed('/api/auth/users/list', 'read') && allowed('/api/auth/users/create', 'write'),
    canViewRoles: allowed('/api/auth/rbac/catalog/roles', 'read'),
    canManageRoles: allowed('/api/auth/rbac/catalog/roles', 'write'),
    canViewModels: allowed('/api/models/catalog', 'read'),
    canManageModels: allowed('/api/models', 'write'),
    canManageChannelBindingsGlobally: allowed('/api/auth/users/list', 'write'),
    requiresLoginMessage: '登录后可使用此功能。',
  }
}

export function isUnauthorizedErrorMessage(message: string): boolean {
  return message.includes('HTTP 401') || message.includes('登录状态已失效')
}

/**
 * 判断请求错误是否为 401，兼容带状态码与仅含文案两种来源。
 *
 * Args:
 *   error: 捕获到的异常。
 *
 * Returns:
 *   boolean: 未授权时返回 true。
 */
export function isUnauthorizedError(error: unknown): boolean {
  if (error instanceof Error) {
    const status = (error as Error & { status?: number }).status
    if (status === 401) return true
    return isUnauthorizedErrorMessage(error.message)
  }
  return false
}

export interface AuthRuntimeConfig {
  allowGuest: boolean
  allowRegistration: boolean
}

let authRuntimeConfigPromise: Promise<AuthRuntimeConfig> | null = null

/**
 * 获取后端公开的认证策略开关，拉取失败时按允许游客处理，避免锁死页面。
 *
 * Args:
 *   无。
 *
 * Returns:
 *   Promise<AuthRuntimeConfig>: 游客与注册开关。
 */
export function fetchAuthRuntimeConfig(): Promise<AuthRuntimeConfig> {
  if (!authRuntimeConfigPromise) {
    authRuntimeConfigPromise = fetchJson<{
      allow_guest?: boolean
      allow_registration?: boolean
    }>(getApiUrl(AUTH_CONFIG_API_PATH))
      .then((payload) => ({
        allowGuest: payload.allow_guest !== false,
        allowRegistration: payload.allow_registration !== false,
      }))
      .catch(() => ({ allowGuest: true, allowRegistration: true }))
  }
  return authRuntimeConfigPromise
}

/**
 * 跳转到登录页并携带返回地址；已在登录页时不重复跳转。
 *
 * Args:
 *   无。
 *
 * Returns:
 *   无。
 */
export function redirectToLogin(): void {
  if (typeof window === 'undefined') return
  if (window.location.pathname === '/login') return
  const next = `${window.location.pathname}${window.location.search}${
    window.location.hash || '#/chat'
  }`
  window.location.assign(`/login?next=${encodeURIComponent(next)}`)
}

export function getStoredAuthToken(): string {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || ''
}

export function storeAuthToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export function clearStoredAuthToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

export function getRememberedLogin(): RememberedLogin | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(AUTH_REMEMBER_LOGIN_STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as Partial<RememberedLogin>
    const username =
      typeof parsed.username === 'string' ? parsed.username.trim().toLowerCase() : ''
    const password = typeof parsed.password === 'string' ? parsed.password : ''
    if (!username || !password) return null
    return { username, password }
  } catch {
    return null
  }
}

export function storeRememberedLogin(login: RememberedLogin): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(
    AUTH_REMEMBER_LOGIN_STORAGE_KEY,
    JSON.stringify({
      username: login.username.trim().toLowerCase(),
      password: login.password,
    })
  )
}

export function clearRememberedLogin(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(AUTH_REMEMBER_LOGIN_STORAGE_KEY)
}

export async function submitAuthRequest(
  mode: 'login' | 'register',
  username: string,
  password: string,
  email?: string
): Promise<AuthLoginResponse> {
  const payload: Record<string, string> = { username, password }
  const normalizedEmail = email?.trim()
  if (normalizedEmail) payload.email = normalizedEmail
  return fetchJson<AuthLoginResponse>(
    getApiUrl(mode === 'login' ? AUTH_LOGIN_API_PATH : AUTH_REGISTER_API_PATH),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  )
}

export async function fetchCurrentActor(token: string): Promise<ActorState> {
  const payload = await fetchJson<ActorPayload>(getApiUrl(AUTH_ME_API_PATH), {
    headers: buildAuthorizationHeaders(token),
  })
  return normalizeActorPayload(payload)
}

export async function revokeAuthToken(token: string): Promise<void> {
  if (!token.trim()) return
  await fetchJson<void>(getApiUrl(AUTH_LOGOUT_API_PATH), {
    method: 'POST',
    headers: buildAuthorizationHeaders(token),
  })
}
