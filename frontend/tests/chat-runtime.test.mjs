import test from 'node:test'
import assert from 'node:assert/strict'

import utilsPkg from '../.tmp-test/utils.js'

const { createClearedChatState } = utilsPkg

test('createClearedChatState clears interrupt state and creates a new session id', () => {
  const state = createClearedChatState()

  assert.equal(state.showInterrupt, false)
  assert.equal(state.interruptData, null)
  assert.equal(typeof state.sessionId, 'string')
  assert.ok(state.sessionId.length > 0)
})
