import test from 'node:test'
import assert from 'node:assert/strict'
import { registerHooks, createRequire } from 'node:module'
import { readFileSync, existsSync, writeFileSync } from 'node:fs'
import ts from 'typescript'

// 加载实际 TS/TSX 组件，验证数据恢复和渲染结果。
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('.') && context.parentURL?.includes('/components/')) {
      const base = new URL(specifier, context.parentURL)
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const candidate = new URL(base.href + suffix)
        if (existsSync(candidate)) return { url: candidate.href, shortCircuit: true }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.css')) {
      const keys = [...readFileSync(new URL(url), 'utf8').matchAll(/\.([a-zA-Z_][\w-]*)/g)].map((match) => match[1])
      return {
        format: 'module', shortCircuit: true,
        source: `export default ${JSON.stringify(Object.fromEntries(keys.map((key) => [key, key])))}`,
      }
    }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(new URL(url), 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return nextLoad(url, context)
  },
})
const { toHistoryMessages, mergeAssistantProcessSnapshot, recordToolDecisions, resumeAssistantMessage, createThreadRuntime } = await import('../components/chat/utils/chatRuntime.ts')
const { useChatRuntime } = await import('../components/chat/hooks/useChatRuntime.ts')
const { getAssistantMessageItems } = await import('../components/chat/utils/assistantMessage.ts')
const { ProcessSummary } = await import('../components/chat/cards/ProcessSummary.tsx')
const { ToolCard } = await import('../components/chat/cards/ToolCard.tsx')
const { InterruptPanel } = await import('../components/chat/interrupt/InterruptPanel.tsx')
const { InterruptArgFields } = await import('../components/chat/interrupt/InterruptArgFields.tsx')
const { isDecisionAllowedForAllActions, updateValueAtPath } = await import('../components/chat/interrupt/utils.ts')
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

const snapshot = [
  { id: 'u1', role: 'user', content: '查询天气' },
  { id: 'r1', role: 'reasoning', content: '先查询天气' },
  { id: 'a1', role: 'assistant', content: '', toolCalls: [
    { id: 't1', type: 'function', function: { name: 'weather', arguments: '{"city":"北京"}' } },
  ] },
  { id: 'o1', role: 'tool', toolCallId: 't1', content: '晴天' },
  { id: 'a2', role: 'assistant', content: '北京晴天' },
]
const placeholder = () => ({ id: 'local', role: 'ai', content: '', startedAt: 1000 })

test('审批面板展示参数、操作层级和受限权限，并保留嵌套编辑能力', () => {
  const data = {
    interrupt_id: 'i1',
    action_requests: [{ name: 'get_weather', description: '工具执行等待批准', args: { location: '南阳' } }],
    review_configs: [{ action_name: 'get_weather', allowed_decisions: ['approve', 'reject'] }],
  }
  const html = renderToStaticMarkup(React.createElement(InterruptPanel, {
    showInterrupt: true, interruptData: data, onInterruptAction() {}, onAskUserResponse() {},
  }))
  assert.match(html, /确认后继续/)
  assert.match(html, /等待确认/)
  assert.match(html, /南阳/)
  assert.match(html, /批准执行/)
  assert.doesNotMatch(html, /工具执行等待批准/)
  assert.match(html, /disabled=""[^>]*>编辑参数/)
  assert.equal(isDecisionAllowedForAllActions(data, 'edit'), false)
  const args = { filters: [{ city: '南阳', count: 2 }] }
  const updated = updateValueAtPath(args, ['filters', 0, 'city'], '北京')
  assert.equal(updated.filters[0].city, '北京')
  assert.equal(args.filters[0].city, '南阳')
  const editable = renderToStaticMarkup(React.createElement(InterruptArgFields, {
    value: args, path: [], disabled: false, onChange() {},
  }))
  assert.match(editable, /type="number"/)
  assert.match(editable, /value="南阳"/)
  const hidden = renderToStaticMarkup(React.createElement(InterruptPanel, {
    showInterrupt: false, interruptData: data, onInterruptAction() {}, onAskUserResponse() {},
  }))
  assert.equal(hidden, '')
  if (process.env.DEEPCLAW_APPROVAL_PREVIEW) {
    data.review_configs[0].allowed_decisions.push('edit')
    const preview = renderToStaticMarkup(React.createElement(InterruptPanel, {
      showInterrupt: true, interruptData: data, onInterruptAction() {}, onAskUserResponse() {},
    }))
    const css = readFileSync(new URL('../components/chat/interrupt/InterruptPanel.module.css', import.meta.url), 'utf8')
    writeFileSync(process.env.DEEPCLAW_APPROVAL_PREVIEW, `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0;padding:60px 24px;background:#f7f9fb;font-family:"Segoe UI","Microsoft YaHei",sans-serif}main{max-width:880px;margin:auto}*{box-sizing:border-box}${css}</style><main>${preview}</main></html>`)
  }
})

test('人工提问保留选项和自定义回答能力', () => {
  const html = renderToStaticMarkup(React.createElement(InterruptPanel, {
    showInterrupt: true,
    interruptData: { action_requests: [{ name: 'ask_user', args: {
      question: '选择查询范围', options: [{ label: '今天', description: '仅查询今天' }], custom: true,
    } }] },
    onInterruptAction() {}, onAskUserResponse() {},
  }))
  assert.match(html, /选择查询范围/)
  assert.match(html, /仅查询今天/)
  assert.match(html, /输入自己的答案/)
})

/**
 * 用真实 Hook 和模拟 SSE 验证人工审批恢复链路。
 *
 * Args:
 *   无。
 */
function createResumeHarness() {
  const runtime = createThreadRuntime('thread')
  runtime.runId = 'run'
  const state = { processing: false, status: 'ready', retry: null }
  const message = {
    ...placeholder(), duration: 500,
    content: '正在查询。',
    contentBlocks: [{ id: 'local_content_1', content: '正在查询。' }],
    reasoningContent: '需要天气工具。',
    reasoningBlocks: [{ id: 'local_reasoning_1', content: '需要天气工具。' }],
    messageItems: [
      { id: 'r1', type: 'reasoning', reasoningBlockId: 'local_reasoning_1' },
      { id: 'c1', type: 'content', contentBlockId: 'local_content_1' },
      { id: 't1', type: 'tool', toolCallId: 't1' },
    ],
    toolData: [{ toolCall: { id: 't1', name: 'get_weather', args: { location: '南阳' } }, approvalStatus: 'pending' }],
  }
  const noop = () => {}
  const deps = new Proxy({
    messages: [{ id: 'u1', role: 'user', content: '南阳天气' }, message],
    interruptData: { interrupt_id: 'interrupt-1', action_requests: [{ name: 'get_weather' }] },
    aguiApiPath: '/api/agui/runs',
    activeThreadIdRef: { current: 'thread' },
    streamGenerationRef: { current: 0 },
    messagesRef: { current: [] },
    currentAssistantMessageIdRef: { current: 'local' },
    currentRunIdRef: { current: 'run' },
    currentRunInputRef: { current: { messages: [{ id: 'u1', role: 'user', content: '南阳天气' }] } },
    requestModeRef: { current: 'agent' },
    requestKnowledgeBaseRef: { current: null },
    lastAssistantStreamEventRef: { current: null },
    reasoningBlockCounterRef: { current: 1 },
    contentBlockCounterRef: { current: 1 },
    reasoningStartTimeRef: { current: null },
    toolCallStartTimesRef: { current: {} },
    toolCallArgsRef: { current: {} },
    processedToolCallIdsRef: { current: new Set() },
    lastEventIdRef: { current: null },
    abortControllerRef: { current: null },
    getThreadRuntime: () => runtime,
    withAuthHeaders: (headers) => headers,
    setIsProcessing: (value) => { state.processing = value },
    setStatus: (value) => { state.status = value },
    requestJson: async () => ({ messages: [] }),
    loadHistorySessions: async () => {},
    registerRetryAction: (_, action) => { state.retry = action },
    applyAssistantError: (_, error) => {
      deps.updateAssistantMessage((current) => ({ ...current, error: error.chatError }))
    },
    updateAssistantMessage: (update) => {
      deps.messagesRef.current = deps.messagesRef.current.map((current) => current.id === 'local' ? update(current) : current)
    },
    setMessagesAndRef: (update) => {
      deps.messagesRef.current = typeof update === 'function' ? update(deps.messagesRef.current) : update
    },
    addMessage: (next) => { deps.messagesRef.current.push(next) },
  }, { get: (target, key) => key in target ? target[key] : noop })
  deps.messagesRef.current = deps.messages
  let actions
  function Harness() {
    actions = useChatRuntime(deps)
    return null
  }
  renderToStaticMarkup(React.createElement(Harness))
  return { actions, deps, state, runtime }
}

test('真实审批恢复链路不追加用户消息或等待气泡，并保持内容块唯一', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  globalThis.window = { location: { origin: 'http://localhost' } }
  try {
    for (const decision of ['approve', 'reject']) {
      const harness = createResumeHarness()
      let posted
      globalThis.fetch = async (url, init) => {
        if (url.endsWith('/resume')) {
          posted = JSON.parse(init.body)
          return Response.json({ runId: 'run' })
        }
        const events = [
          { type: 'TOOL_CALL_RESULT', toolCallId: 't1', content: decision === 'approve' ? '晴天' : '用户已拒绝执行。' },
          { type: 'REASONING_MESSAGE_CONTENT', delta: '整理结果。' },
          { type: 'REASONING_MESSAGE_END' },
          { type: 'TEXT_MESSAGE_CONTENT', delta: '已处理。' },
          { type: 'RUN_FINISHED' },
        ]
        return new Response(events.map((event, index) => `id: run:${index + 1}\ndata: ${JSON.stringify(event)}\n\n`).join(''))
      }
      await harness.actions.handleInterruptAction(decision)
      const messages = harness.deps.messagesRef.current
      assert.equal(messages.length, 2)
      assert.equal(messages.filter((message) => message.role === 'user').length, 1)
      assert.equal(posted.resume[0].interruptId, 'interrupt-1')
      assert.equal(posted.resume[0].payload.decisions[0].type, decision)
      const assistant = messages[1]
      assert.equal(assistant.content, '正在查询。已处理。')
      assert.equal(assistant.toolData[0].toolOutput.length, 2)
      assert.equal(new Set(assistant.contentBlocks.map((block) => block.id)).size, 2)
      assert.equal(new Set(assistant.reasoningBlocks.map((block) => block.id)).size, 2)
      assert.equal(harness.state.processing, false)
      assert.equal(harness.state.status, 'ready')
      assert.equal(harness.runtime.processing, false)
    }
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
  }
})

test('审批恢复失败结束等待，重试复用原 interrupt 和决定', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  globalThis.window = { location: { origin: 'http://localhost' } }
  try {
    const harness = createResumeHarness()
    const requests = []
    globalThis.fetch = async (_, init) => {
      requests.push(JSON.parse(init.body).resume)
      return Response.json({ detail: '服务暂不可用' }, { status: 503 })
    }
    await harness.actions.handleInterruptAction('reject')
    assert.equal(harness.state.processing, false)
    assert.equal(harness.state.status, 'error')
    assert.equal(harness.deps.messagesRef.current[1].error.kind, 'resume')
    await harness.state.retry()
    assert.deepEqual(requests[1], requests[0])
    assert.equal(harness.deps.messagesRef.current.length, 2)
    assert.equal(harness.deps.messagesRef.current[1].toolData[0].toolOutput.length, 1)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
  }
})

test('浏览器时钟记录恢复工具与思考耗时，重复事件不能重置计时', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const originalNow = Date.now
  let now = 100000
  Date.now = () => now
  globalThis.window = { location: { origin: 'http://localhost' } }
  try {
    const harness = createResumeHarness()
    const steps = [
      [101000, { type: 'TOOL_CALL_START', toolCallId: 't1', toolCallName: 'get_weather' }],
      [103000, { type: 'TOOL_CALL_START', toolCallId: 't1', toolCallName: 'get_weather' }],
      [107000, { type: 'TOOL_CALL_RESULT', toolCallId: 't1', content: '晴天', duration: 999999 }],
      [109000, { type: 'TOOL_CALL_RESULT', toolCallId: 't1', content: '晴天' }],
      [110000, { type: 'REASONING_MESSAGE_CONTENT', delta: '整理' }],
      [112000, { type: 'REASONING_MESSAGE_CONTENT', delta: '结果' }],
      [115000, { type: 'REASONING_MESSAGE_END' }],
      [116000, { type: 'RUN_FINISHED' }],
    ]
    globalThis.fetch = async (url) => {
      if (url.endsWith('/resume')) return Response.json({ runId: 'run' })
      let index = 0
      return new Response(new ReadableStream({
        pull(controller) {
          if (index === steps.length) return controller.close()
          const [time, event] = steps[index++]
          now = time
          controller.enqueue(new TextEncoder().encode(`id: run:${index}\ndata: ${JSON.stringify(event)}\n\n`))
        },
      }, { highWaterMark: 0 }))
    }
    await harness.actions.handleInterruptAction('approve')
    const assistant = harness.deps.messagesRef.current[1]
    assert.equal(assistant.toolData[0].startedAt, 100000)
    assert.equal(assistant.toolData[0].duration, 7000)
    assert.equal(assistant.reasoningBlocks.at(-1).startedAt, 110000)
    assert.equal(assistant.reasoningBlocks.at(-1).duration, 5000)
    assert.equal(assistant.duration, 16500)
    assert.equal(assistant.toolData[0].toolOutput.length, 2)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
    Date.now = originalNow
  }
})

test('批准后即使没有工具开始事件也用前端时间计时，拒绝不生成执行耗时', async () => {
  const originalFetch = globalThis.fetch
  const originalWindow = globalThis.window
  const originalNow = Date.now
  globalThis.window = { location: { origin: 'http://localhost' } }
  try {
    for (const decision of ['approve', 'reject']) {
      let now = 50000
      Date.now = () => now
      const harness = createResumeHarness()
      globalThis.fetch = async (url) => {
        if (url.endsWith('/resume')) return Response.json({ runId: 'run' })
        now = 53000
        return new Response([
          { type: 'TOOL_CALL_RESULT', toolCallId: 't1', content: '结果' },
          { type: 'RUN_FINISHED' },
        ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''))
      }
      await harness.actions.handleInterruptAction(decision)
      assert.equal(harness.deps.messagesRef.current[1].toolData[0].duration, decision === 'approve' ? 3000 : undefined)
    }
  } finally {
    globalThis.fetch = originalFetch
    globalThis.window = originalWindow
    Date.now = originalNow
  }
})

test('执行中的思考和工具显示实时耗时，人工等待和历史缺失计时不展示伪造值', () => {
  const originalNow = Date.now
  Date.now = () => 10000
  try {
    const msg = {
      ...placeholder(),
      reasoningBlocks: [{ id: 'r', content: '思考内容', startedAt: 5000 }],
      toolData: [{ toolCall: { id: 't', name: 'weather', args: {} }, startedAt: 7000 }],
    }
    const render = (message, isProcessing) => renderToStaticMarkup(React.createElement(ProcessSummary, {
      msg: message, reasoningBlocks: message.reasoningBlocks, isProcessing,
      toolCallDurations: { t: 88888 },
    }))
    const html = render(msg, true)
    assert.match(html, /reasoningDuration[^>]*>5s</)
    assert.match(html, /toolDuration[^>]*>3s</)
    const pending = render({ ...msg, toolData: [{ ...msg.toolData[0], approvalStatus: 'pending' }] }, true)
    assert.doesNotMatch(pending, /toolDuration/)
    const history = render({ ...msg, startedAt: undefined,
      reasoningBlocks: [{ id: 'r', content: '思考内容' }],
      toolData: [{ toolCall: msg.toolData[0].toolCall }],
    }, false)
    assert.doesNotMatch(history, /reasoningDuration|toolDuration|总耗时/)
  } finally {
    Date.now = originalNow
  }
})

test('批准和拒绝写入工具输出，恢复沿用原 assistant 且不复制审批决定', () => {
  for (const decision of [{ type: 'approve' }, { type: 'reject', message: '用户已拒绝执行。' }]) {
    const message = {
      ...placeholder(), duration: 500,
      toolData: [{ toolCall: { id: 't1', name: 'get_weather', args: { location: '南阳' } } }],
    }
    const actions = [{ name: 'get_weather' }]
    const decided = recordToolDecisions(message, actions, [decision])
    const repeated = recordToolDecisions(decided, actions, [decision])
    assert.equal(repeated.toolData[0].toolOutput.length, 1)
    assert.equal(repeated.toolData[0].toolOutput[0].kind, 'decision')
    assert.match(repeated.toolData[0].toolOutput[0].content, decision.type === 'approve' ? /批准/ : /拒绝/)
    const resumed = resumeAssistantMessage(repeated, 5000)
    assert.equal(resumed.id, message.id)
    assert.equal(resumed.role, 'ai')
    assert.equal(resumed.startedAt, 4500)
    assert.equal(resumed.duration, undefined)
    assert.equal(message.toolData[0].toolOutput, undefined)
    const html = renderToStaticMarkup(React.createElement(ToolCard, { toolData: resumed.toolData[0] }))
    assert.doesNotMatch(html, /工具执行成功/)
    assert.match(html, decision.type === 'approve' ? /等待工具结果/ : /已拒绝/)
  }
})

test('同名工具只更新本次待审批调用，参数编辑和执行结果都保留', () => {
  const message = {
    ...placeholder(),
    toolData: [
      { toolCall: { id: 'old', name: 'weather', args: {} }, toolOutput: [{ tool_call_id: 'old', content: '旧结果' }] },
      { toolCall: { id: 't1', name: 'weather', args: {} }, approvalStatus: 'pending' },
    ],
  }
  const edited = recordToolDecisions(message, [{ name: 'weather' }], [
    { type: 'edit', edited_action: { name: 'weather', args: { city: '北京' } } },
  ])
  assert.deepEqual(edited.toolData[1].toolCall.args, { city: '北京' })
  assert.equal(edited.toolData[0], message.toolData[0])
  const completed = mergeAssistantProcessSnapshot(edited, snapshot, 'u1')
  assert.equal(completed.toolData[1].toolOutput.length, 2)
  assert.equal(completed.toolData[1].toolOutput[1].content, '晴天')
  const repeated = mergeAssistantProcessSnapshot(completed, snapshot, 'u1')
  assert.equal(repeated.toolData[1].toolOutput.length, 2)
})

test('快照恢复本轮思考、工具参数和结果，重复快照不重复展示', () => {
  const message = mergeAssistantProcessSnapshot(placeholder(), snapshot, 'u1')
  assert.equal(message.reasoningContent, '先查询天气')
  assert.deepEqual(message.toolData[0].toolCall.args, { city: '北京' })
  assert.equal(message.toolData[0].toolOutput[0].content, '晴天')
  assert.equal(message.id, 'local')
  assert.equal(message.startedAt, 1000)
  assert.equal(message.duration, undefined)
  const repeated = mergeAssistantProcessSnapshot(message, snapshot, 'u1')
  assert.equal(repeated.reasoningBlocks.length, 1)
  assert.equal(repeated.toolData.length, 1)
  assert.equal(repeated.messageItems.length, 2)
})

test('起始快照不会串入上一轮思考和工具', () => {
  const message = placeholder()
  assert.equal(mergeAssistantProcessSnapshot(message, snapshot, 'u2'), message)
  assert.equal(mergeAssistantProcessSnapshot(message, snapshot, undefined), message)
})

test('快照补齐丢失的思考尾段并保留已有耗时', () => {
  const streamed = {
    ...placeholder(), reasoningContent: '先查询',
    reasoningBlocks: [{ id: 'r', content: '先查询', duration: 50 }],
    messageItems: [{ id: 'ri', type: 'reasoning', reasoningBlockId: 'r' }],
  }
  const completed = mergeAssistantProcessSnapshot(streamed, snapshot, 'u1')
  assert.equal(completed.reasoningContent, '先查询天气')
  assert.equal(completed.reasoningBlocks[0].content, '先查询天气')
  assert.equal(completed.reasoningBlocks[0].duration, 50)
  assert.equal(completed.reasoningBlocks.length, 1)
})

test('结束快照保留流式过程和浏览器耗时', () => {
  const streamed = { ...mergeAssistantProcessSnapshot(placeholder(), snapshot, 'u1'), duration: 300 }
  streamed.reasoningBlocks[0].duration = 50
  streamed.toolData[0].duration = 100
  const completed = mergeAssistantProcessSnapshot(streamed, snapshot, 'u1')
  assert.equal(completed.duration, 300)
  assert.equal(completed.reasoningBlocks[0].duration, 50)
  assert.equal(completed.toolData[0].duration, 100)
})

test('历史结构化思考能恢复，且不混入回答正文', () => {
  const messages = toHistoryMessages([
    { id: 'u1', type: 'human', content: '你好' },
    { id: 'a1', type: 'ai', content: [
      { type: 'thinking', thinking: '思考一' },
      { type: 'reasoning', reasoning: '思考二' },
      { type: 'reasoning', summary: [{ type: 'summary_text', text: '思考三' }] },
      { type: 'text', text: '你好！' },
    ] },
  ])
  assert.equal(messages[1].reasoningContent, '思考一思考二思考三')
  assert.equal(messages[1].content, '你好！')
})

test('已有正文展示项时仍补齐缺失的过程展示项', () => {
  const message = mergeAssistantProcessSnapshot(placeholder(), snapshot, 'u1')
  message.content = '北京晴天'
  message.messageItems = [{ id: 'c', type: 'content', contentBlockId: 'local_content_legacy' }]
  const items = getAssistantMessageItems(message)
  assert.equal(items.filter((item) => item.type === 'reasoning').length, 1)
  assert.equal(items.filter((item) => item.type === 'tool').length, 1)
  assert.equal(items.filter((item) => item.type === 'content').length, 1)
})

test('处理中及结束后都保留真实思考和工具，无过程时结束后隐藏摘要', () => {
  const message = mergeAssistantProcessSnapshot(placeholder(), snapshot, 'u1')
  for (const isProcessing of [true, false]) {
    const html = renderToStaticMarkup(React.createElement(ProcessSummary, {
      msg: { ...message, duration: isProcessing ? undefined : 300 },
      reasoningBlocks: message.reasoningBlocks, isProcessing,
    }))
    assert.doesNotMatch(html, /先查询天气/)
    assert.match(html, /reasoningHeader[^>]*aria-expanded="false"/)
    assert.match(html, /weather/)
    assert.match(html, /aria-expanded="true"/)
  }
  const html = renderToStaticMarkup(React.createElement(ProcessSummary, {
    msg: { ...placeholder(), duration: 300 }, reasoningBlocks: [], isProcessing: false,
  }))
  assert.equal(html, '')
  const historyHtml = renderToStaticMarkup(React.createElement(ProcessSummary, {
    msg: { id: 'history', role: 'ai', content: '你好' }, reasoningBlocks: [], isProcessing: false,
  }))
  assert.equal(historyHtml, '')
  const waitingHtml = renderToStaticMarkup(React.createElement(ProcessSummary, {
    msg: placeholder(), reasoningBlocks: [], isProcessing: true,
  }))
  assert.match(waitingHtml, /正在处理中/)
  assert.doesNotMatch(waitingHtml, /等待模型返回|未返回思考|processSummaryDetails/)
})
