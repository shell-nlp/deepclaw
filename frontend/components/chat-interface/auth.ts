import {
  AUTH_LOGIN_API_PATH,
  AUTH_LOGOUT_API_PATH,
  AUTH_ME_API_PATH,
  AUTH_REGISTER_API_PATH,
  AUTH_TOKEN_STORAGE_KEY,
} from './constants'
import type { AuthLoginResponse, AuthUserSummary } from './types'
import { fetchJson, getApiUrl } from './utils'

export const GUEST_USER_ID = 'guest'

export type ActorRole = 'guest' | 'user' | 'admin'

export interface ActorState {
  isGuest: boolean
  userId: string
  email: string | null
  role: ActorRole
}

export interface ActorPayload {
  is_guest?: boolean
  user_id?: string | null
  email?: string | null
  role?: string | null
}

export interface ActorCapabilities {
  canManageKnowledge: boolean
  canManageSkills: boolean
  canManageUsers: boolean
  requiresLoginMessage: string
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
      email: null,
      role: 'guest',
    }
  }

  const role = payload.role === 'admin' ? 'admin' : 'user'
  return {
    isGuest: false,
    userId: payload.user_id,
    email: payload.email ?? null,
    role,
  }
}

export function normalizeUserToActor(user: AuthUserSummary): ActorState {
  return normalizeActorPayload({
    is_guest: false,
    user_id: user.user_id,
    email: user.email,
    role: user.role,
  })
}

export function getActorCapabilities(actor: ActorState): ActorCapabilities {
  const isSignedIn = !actor.isGuest
  return {
    canManageKnowledge: isSignedIn,
    canManageSkills: isSignedIn,
    canManageUsers: actor.role === 'admin',
    requiresLoginMessage: '登录后可使用此功能。',
  }
}

export function isUnauthorizedErrorMessage(message: string): boolean {
  return message.includes('HTTP 401') || message.includes('登录状态已失效')
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

export async function submitAuthRequest(
  mode: 'login' | 'register',
  email: string,
  password: string
): Promise<AuthLoginResponse> {
  return fetchJson<AuthLoginResponse>(
    getApiUrl(mode === 'login' ? AUTH_LOGIN_API_PATH : AUTH_REGISTER_API_PATH),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
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
