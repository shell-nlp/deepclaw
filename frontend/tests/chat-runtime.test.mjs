import test from 'node:test'
import assert from 'node:assert/strict'

import * as utilsPkg from '../components/chat-interface/utils.ts'

const { createClearedChatState, normalizeChartMarkdown } = utilsPkg

test('createClearedChatState clears interrupt state and creates a new session id', () => {
  const state = createClearedChatState()

  assert.equal(state.showInterrupt, false)
  assert.equal(state.interruptData, null)
  assert.equal(typeof state.sessionId, 'string')
  assert.ok(state.sessionId.length > 0)
})

test('normalizeChartMarkdown rewrites chart origin to the current browser origin', () => {
  const originalWindow = globalThis.window
  globalThis.window = { location: { origin: 'http://10.0.0.8:8088' } }
  try {
    const toolData = [
      {
        toolCall: { id: 'chart-1', name: 'generate_chart', args: {} },
        toolOutput: [
          {
            tool_call_id: 'chart-1',
            content: '![](http://127.0.0.1:7869/charts/abc.png)',
          },
        ],
      },
    ]

    const result = normalizeChartMarkdown(
      '![图表](http://127.0.0.1:7869/charts/abc.png)',
      toolData
    )

    assert.equal(result, '![图表](http://10.0.0.8:8088/charts/abc.png)')
  } finally {
    globalThis.window = originalWindow
  }
})

test('normalizeChartMarkdown maps rewritten chart links by png filename', () => {
  const originalWindow = globalThis.window
  globalThis.window = { location: { origin: 'http://192.168.1.10:9000' } }
  try {
    const toolData = [
      {
        toolCall: { id: 'chart-2', name: 'generate_chart', args: {} },
        toolOutput: [
          {
            tool_call_id: 'chart-2',
            content: '![](/deepclaw/charts/def.png)',
          },
        ],
      },
    ]

    const result = normalizeChartMarkdown('![图表](/charts/def.png)', toolData)

    assert.equal(
      result,
      '![图表](http://192.168.1.10:9000/deepclaw/charts/def.png)'
    )
  } finally {
    globalThis.window = originalWindow
  }
})
