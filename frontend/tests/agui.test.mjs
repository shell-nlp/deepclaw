import test from 'node:test'
import assert from 'node:assert/strict'

import * as aguiPkg from '../components/chat-interface/agui.ts'

test('agui parses serialized HITL interrupt payloads', () => {
  const interrupt = aguiPkg.getAgUiInterrupt({
    type: 'CUSTOM',
    name: 'on_interrupt',
    value: JSON.stringify({
      action_requests: [
        {
          name: 'ask_user',
          description: '请选择继续方式',
          args: { question: '请选择继续方式' },
        },
      ],
      review_configs: [
        {
          action_name: 'ask_user',
          allowed_decisions: ['respond'],
        },
      ],
    }),
  })

  assert.equal(interrupt?.action_requests?.[0]?.name, 'ask_user')
  assert.equal(interrupt?.review_configs?.[0]?.allowed_decisions[0], 'respond')
})

test('agui normalizes raw ask_user interrupt payloads', () => {
  const interrupt = aguiPkg.getAgUiInterrupt({
    type: 'CUSTOM',
    name: 'on_interrupt',
    value: JSON.stringify({
      question: '请选择颜色',
      options: [{ label: '蓝色', description: '冷静' }],
      custom: true,
    }),
  })

  assert.equal(interrupt?.action_requests?.[0]?.name, 'ask_user')
  assert.equal(interrupt?.action_requests?.[0]?.args?.question, '请选择颜色')
  assert.equal(interrupt?.review_configs?.[0]?.allowed_decisions[0], 'respond')
})

test('agui reads standard interrupt outcome and keeps interrupt id', () => {
  const interrupt = aguiPkg.getAgUiInterruptOutcome({
    type: 'RUN_FINISHED',
    outcome: {
      type: 'interrupt',
      interrupts: [
        {
          id: 'interrupt-1',
          reason: 'langgraph:interrupt',
          metadata: {
            langgraph: {
              raw: {
                question: '请选择颜色',
                options: [{ label: '蓝色', description: '冷静' }],
                custom: true,
              },
            },
          },
        },
      ],
    },
  })

  assert.equal(interrupt?.interrupt_id, 'interrupt-1')
  assert.equal(interrupt?.action_requests?.[0]?.name, 'ask_user')
  assert.equal(interrupt?.action_requests?.[0]?.args?.question, '请选择颜色')
})

test('agui ignores malformed interrupt values', () => {
  const interrupt = aguiPkg.getAgUiInterrupt({
    type: 'CUSTOM',
    name: 'on_interrupt',
    value: 'not-json',
  })

  assert.equal(interrupt, null)
})

test('agui reads token usage from LangChain message metadata', () => {
  const usage = aguiPkg.getTokenUsageFromMessage({
    type: 'ai',
    usage_metadata: {
      input_tokens: 120,
      output_tokens: 36,
      total_tokens: 156,
    },
  })

  assert.deepEqual(usage, {
    inputTokens: 120,
    outputTokens: 36,
    totalTokens: 156,
  })
})

test('agui sums token usage for the latest assistant turn', () => {
  const usage = aguiPkg.getLatestAssistantTurnTokenUsage([
    {
      type: 'human',
      content: 'first',
    },
    {
      type: 'ai',
      usage_metadata: {
        input_tokens: 10,
        output_tokens: 2,
        total_tokens: 12,
      },
    },
    {
      type: 'human',
      content: 'latest',
    },
    {
      type: 'ai',
      usage_metadata: {
        input_tokens: 20,
        output_tokens: 4,
        total_tokens: 24,
      },
    },
    {
      type: 'ai',
      usage_metadata: {
        input_tokens: 30,
        output_tokens: 6,
        total_tokens: 36,
      },
    },
  ])

  assert.deepEqual(usage, {
    inputTokens: 50,
    outputTokens: 10,
    totalTokens: 60,
  })
})
