import test from 'node:test'
import assert from 'node:assert/strict'

import * as authPkg from '../components/chat-interface/auth.ts'

test('auth helpers build bearer headers only when token exists', () => {
  assert.equal(typeof authPkg.buildAuthorizationHeaders, 'function')
  assert.deepEqual(authPkg.buildAuthorizationHeaders('token-123'), {
    Authorization: 'Bearer token-123',
  })
  assert.deepEqual(authPkg.buildAuthorizationHeaders(''), {})
})

test('auth helpers normalize guest and authenticated actors', () => {
  assert.equal(typeof authPkg.normalizeActorPayload, 'function')

  assert.deepEqual(authPkg.normalizeActorPayload(null), {
    isGuest: true,
    userId: 'guest',
    email: null,
    role: 'guest',
  })

  assert.deepEqual(
    authPkg.normalizeActorPayload({
      is_guest: false,
      user_id: 'user_123',
      email: 'user@example.com',
      role: 'admin',
    }),
    {
      isGuest: false,
      userId: 'user_123',
      email: 'user@example.com',
      role: 'admin',
    }
  )
})

test('auth helpers expose guest write restrictions and admin flag', () => {
  assert.equal(typeof authPkg.getActorCapabilities, 'function')

  const guest = authPkg.getActorCapabilities({
    isGuest: true,
    userId: 'guest',
    email: null,
    role: 'guest',
  })
  const admin = authPkg.getActorCapabilities({
    isGuest: false,
    userId: 'user_1',
    email: 'admin@example.com',
    role: 'admin',
  })

  assert.equal(guest.canManageKnowledge, false)
  assert.equal(guest.canManageSkills, false)
  assert.equal(guest.canManageUsers, false)
  assert.equal(guest.requiresLoginMessage, '登录后可使用此功能。')
  assert.equal(admin.canManageUsers, true)
})

test('auth helpers detect expired or invalid auth responses', () => {
  assert.equal(typeof authPkg.isUnauthorizedErrorMessage, 'function')
  assert.equal(authPkg.isUnauthorizedErrorMessage('HTTP 401'), true)
  assert.equal(authPkg.isUnauthorizedErrorMessage('登录状态已失效，请重新登录。'), true)
  assert.equal(authPkg.isUnauthorizedErrorMessage('登录后可使用此功能。'), false)
})
test('auth helpers expose channel binding admin capability only to admins', () => {
  const guest = authPkg.getActorCapabilities({
    isGuest: true,
    userId: 'guest',
    email: null,
    role: 'guest',
  })
  const user = authPkg.getActorCapabilities({
    isGuest: false,
    userId: 'user_1',
    email: 'user@example.com',
    role: 'user',
  })
  const admin = authPkg.getActorCapabilities({
    isGuest: false,
    userId: 'admin_1',
    email: 'admin@example.com',
    role: 'admin',
  })

  assert.equal(guest.canManageChannelBindingsGlobally, false)
  assert.equal(user.canManageChannelBindingsGlobally, false)
  assert.equal(admin.canManageChannelBindingsGlobally, true)
})
