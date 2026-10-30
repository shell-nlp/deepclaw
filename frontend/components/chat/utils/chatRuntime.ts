import { DEFAULT_AGUI_API_PATH } from './constants'
import { getTokenUsageFromMessage } from './agui'
import { stringifyToolContent } from './index'
import type {
  AssistantMessageItem,
  ChatError,
  ChatErrorKind,
  ChatStatus,
  InterruptData,
  KnowledgeBase,
  Message,
  ReasoningBlock,
  RequestMode,
  ToolData,
} from './types'

export type AssistantStreamKind = 'reasoning' | 'content' | 'tool' | 'interrupt' | null

export type ThreadRuntime = {
  threadId: string
  agentId: string | null
  messages: Message[]
  basePath: string
  runId: string | null
  runInput: Record<string, unknown> | null
  lastEventId: string | null
  status: ChatStatus
  processing: boolean
  showInterrupt: boolean
  interruptData: InterruptData | null
  toolCallDurations: Record<string, number>
  assistantMessageId: string | null
  processedToolCallIds: string[]
  lastAssistantStreamEvent: AssistantStreamKind
  reasoningStartTime: number | null
  toolCallStartTimes: Record<string, number>
  toolCallArgs: Record<string, string>
  reasoningBlockCounter: number
  contentBlockCounter: number
  requestMode: RequestMode
  requestKnowledgeBase: KnowledgeBase | null
  requestMcpConfig: Record<string, unknown> | null
  abortController: AbortController | null
}

export function createThreadRuntime(threadId: string): ThreadRuntime {
  return {
    threadId,
    agentId: null,
    messages: [],
    basePath: DEFAULT_AGUI_API_PATH,
    runId: null,
    runInput: null,
    lastEventId: null,
    status: 'ready',
    processing: false,
    showInterrupt: false,
    interruptData: null,
    toolCallDurations: {},
    assistantMessageId: null,
    processedToolCallIds: [],
    lastAssistantStreamEvent: null,
    reasoningStartTime: null,
    toolCallStartTimes: {},
    toolCallArgs: {},
    reasoningBlockCounter: 0,
    contentBlockCounter: 0,
    requestMode: 'agent',
    requestKnowledgeBase: null,
    requestMcpConfig: null,
    abortController: null,
  }
}

export function isActiveRunStatus(status: string): boolean {
  return status === 'queued' || status === 'running' || status === 'cancelling'
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  )
}

export class ChatRequestError extends Error {
  readonly chatError: ChatError

  constructor(chatError: ChatError) {
    super(chatError.message)
    this.name = 'ChatRequestError'
    this.chatError = chatError
  }
}

function getChatErrorTitle(kind: ChatErrorKind): string {
  if (kind === 'http') return '请求失败'
  if (kind === 'run') return 'Agent 运行失败'
  if (kind === 'stream') return '事件流中断'
  if (kind === 'resume') return '恢复失败'
  return '请求失败'
}

export function createChatError(
  kind: ChatErrorKind,
  message: string,
  options: {
    status?: number
    detail?: string
    retryable?: boolean
  } = {}
): ChatError {
  return {
    kind,
    title: getChatErrorTitle(kind),
    message: message || '未知错误',
    status: options.status,
    detail: options.detail,
    retryable: options.retryable ?? true,
  }
}

async function readResponseErrorDetail(response: Response): Promise<string> {
  try {
    const text = await response.text()
    if (!text) return ''
    try {
      const parsed = JSON.parse(text) as unknown
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const detail = (parsed as Record<string, unknown>).detail
        if (typeof detail === 'string') return detail
      }
    } catch {
      return text
    }
    return text
  } catch {
    return ''
  }
}

export async function createHttpChatError(
  response: Response,
  kind: Extract<ChatErrorKind, 'http' | 'stream' | 'resume'>
): Promise<ChatError> {
  const detail = await readResponseErrorDetail(response)
  return createChatError(
    kind,
    detail || `HTTP ${response.status}`,
    {
      status: response.status,
      detail: detail || undefined,
      retryable:
        response.status >= 500 ||
        response.status === 408 ||
        response.status === 429,
    }
  )
}

export function toChatError(error: unknown, fallbackKind: ChatErrorKind = 'unknown'): ChatError {
  if (error instanceof ChatRequestError) return error.chatError
  if (error instanceof Error) {
    return createChatError(fallbackKind, error.message || '未知错误')
  }
  return createChatError(fallbackKind, '未知错误')
}

function getHistoryMessageContent(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''

  return content
    .map((item) => {
      if (typeof item === 'string') return item
      if (
        item &&
        typeof item === 'object' &&
        (!('type' in item) || item.type === 'text' || item.type === 'output_text') &&
        'text' in item &&
        typeof item.text === 'string'
      ) {
        return item.text
      }
      return ''
    })
    .join('')
}

/**
 * 提取消息中的思考文本，兼容元数据和结构化内容块。
 *
 * Args:
 *   message: 后端历史消息或 AG-UI 消息。
 */
export function getHistoryReasoningContent(message: Record<string, unknown>): string {
  const additionalKwargs = message.additional_kwargs
  const responseMetadata = message.response_metadata
  const candidates = [
    message.reasoning_content,
    message.reasoning,
    additionalKwargs && typeof additionalKwargs === 'object'
      ? (additionalKwargs as Record<string, unknown>).reasoning_content
      : undefined,
    responseMetadata && typeof responseMetadata === 'object'
      ? (responseMetadata as Record<string, unknown>).reasoning_content
      : undefined,
  ]

  for (const candidate of candidates) {
    const content = getHistoryMessageContent(candidate)
    if (content) return content
  }
  if (!Array.isArray(message.content)) return ''
  return message.content.map((item) => {
    if (!item || typeof item !== 'object') return ''
    const block = item as Record<string, unknown>
    if (block.type === 'thinking') return String(block.thinking || '')
    if (block.type === 'reasoning_content') {
      const value = block.reasoning_content
      return value && typeof value === 'object'
        ? String((value as Record<string, unknown>).text || '') : ''
    }
    if (block.type !== 'reasoning') return ''
    return typeof block.reasoning === 'string'
      ? block.reasoning : Array.isArray(block.summary) ? block.summary.map((part) =>
        part && typeof part === 'object' && typeof part.text === 'string' ? part.text : ''
      ).join('') : ''
  }).join('')
}

function getHistoryToolData(message: Record<string, unknown>): ToolData[] {
  const calls = message.tool_calls ?? message.toolCalls
  if (!Array.isArray(calls)) return []

  return calls.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const raw = item as Record<string, unknown>
    const toolCall = raw.function && typeof raw.function === 'object'
      ? { ...raw, ...(raw.function as Record<string, unknown>), args: (raw.function as Record<string, unknown>).arguments }
      : raw
    if (typeof toolCall.id !== 'string' || typeof toolCall.name !== 'string') {
      return []
    }
    const args: Record<string, unknown> = {}
    if (toolCall.args && typeof toolCall.args === 'object' && !Array.isArray(toolCall.args)) {
      Object.assign(args, toolCall.args)
    } else if (typeof toolCall.args === 'string') {
      try {
        const parsedArgs = JSON.parse(toolCall.args) as unknown
        if (parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs)) {
          Object.assign(args, parsedArgs)
        }
      } catch {
      }
    }
    return [
      {
        toolCall: {
          id: toolCall.id,
          name: toolCall.name,
          args,
        },
        toolOutput: [],
      },
    ]
  })
}

function createHistoryAssistantMessage(
  id: string,
  createdAt?: number
): Message {
  return {
    id,
    role: 'ai',
    content: '',
    createdAt,
    messageItems: [],
    toolData: [],
  }
}

function parseCreatedAt(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1_000_000_000_000 ? value : value * 1000
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) return parsed
  }
  return undefined
}

function resolveMessageCreatedAt(
  messageCreatedAt: unknown,
  messageId: string,
  index: number
): number | undefined {
  // 新版后端把逐条消息时间存成 messageId -> ISO 时间 的映射；
  // 旧数据是按下标对齐的数组，这里同时兼容两种形态。
  if (Array.isArray(messageCreatedAt)) {
    return parseCreatedAt(messageCreatedAt[index])
  }
  if (messageCreatedAt && typeof messageCreatedAt === 'object') {
    return parseCreatedAt(
      (messageCreatedAt as Record<string, unknown>)[messageId]
    )
  }
  return undefined
}

export function toHistoryMessages(
  stateMessages: unknown,
  messageCreatedAt?: unknown,
  fallbackCreatedAt?: number
): Message[] {
  if (!Array.isArray(stateMessages)) return []

  const historyMessages: Message[] = []
  const toolOwnerMessages = new Map<string, Message>()
  let activeAssistant: Message | null = null

  stateMessages.forEach((item, index) => {
    if (!item || typeof item !== 'object') return
    const message = item as Record<string, unknown>
    const messageId =
      typeof message.id === 'string' ? message.id : `history_message_${index}`
    const content = getHistoryMessageContent(message.content)
    const itemCreatedAt = resolveMessageCreatedAt(
      messageCreatedAt,
      messageId,
      index
    )
    const createdAt = itemCreatedAt ?? fallbackCreatedAt
    const role = message.type || message.role
    if (role === 'human' || role === 'user') {
      historyMessages.push({
        id: messageId,
        role: 'user',
        content,
        createdAt,
      })
      activeAssistant = null
      toolOwnerMessages.clear()
      return
    }

    if (role === 'ai' || role === 'assistant' || role === 'reasoning') {
      if (!activeAssistant) {
        activeAssistant = createHistoryAssistantMessage(
          `${messageId}_assistant`,
          createdAt
        )
        historyMessages.push(activeAssistant)
      }
      const reasoningContent = role === 'reasoning'
        ? getHistoryMessageContent(message.content) : getHistoryReasoningContent(message)
      const toolData = getHistoryToolData(message)
      const tokenUsage = getTokenUsageFromMessage(message)
      const assistant = activeAssistant

      if (reasoningContent) {
        const block = { id: `${messageId}_reasoning`, content: reasoningContent }
        assistant.reasoningContent = `${assistant.reasoningContent || ''}${reasoningContent}`
        assistant.reasoningBlocks = [...(assistant.reasoningBlocks || []), block]
        assistant.messageItems?.push({
          id: `reasoning_item_${block.id}`,
          type: 'reasoning',
          reasoningBlockId: block.id,
        })
      }
      if (content && role !== 'reasoning') {
        const block = { id: `${messageId}_content`, content }
        assistant.content = `${assistant.content}${content}`
        assistant.contentBlocks = [...(assistant.contentBlocks || []), block]
        assistant.messageItems?.push({
          id: `content_item_${block.id}`,
          type: 'content',
          contentBlockId: block.id,
        })
      }
      toolData.forEach((tool) => {
        assistant.toolData?.push(tool)
        assistant.messageItems?.push({
          id: `tool_item_${tool.toolCall.id}`,
          type: 'tool',
          toolCallId: tool.toolCall.id,
        })
        toolOwnerMessages.set(tool.toolCall.id, assistant)
      })
      if (tokenUsage) {
        assistant.tokenUsage = tokenUsage
      }
      return
    }

    const toolCallId = message.tool_call_id ?? message.toolCallId
    if (role !== 'tool' || typeof toolCallId !== 'string') return
    const assistant = toolOwnerMessages.get(toolCallId) || activeAssistant
    if (!assistant) {
      const newAssistant = createHistoryAssistantMessage(
        `${messageId}_assistant`,
        createdAt
      )
      historyMessages.push(newAssistant)
      toolOwnerMessages.set(toolCallId, newAssistant)
      activeAssistant = newAssistant
      return
    }
    const toolOutput = { tool_call_id: toolCallId, content: stringifyToolContent(message.content) }
    const tool = assistant.toolData?.find((item) => item.toolCall.id === toolCallId)
    if (!tool) {
      const newTool = {
        toolCall: { id: toolCallId, name: 'tool', args: {} },
        toolOutput: [toolOutput],
      }
      assistant.toolData?.push(newTool)
      assistant.messageItems?.push({
        id: `tool_item_${toolCallId}`,
        type: 'tool',
        toolCallId,
      })
      toolOwnerMessages.set(toolCallId, assistant)
      return
    }
    tool.toolOutput = [...(tool.toolOutput || []), toolOutput]
  })

  return historyMessages
}

/**
 * 用当前轮次的快照补齐过程，保留流式数据、消息标识和浏览器计时。
 *
 * Args:
 *   message: 正在展示的 assistant 消息。
 *   state_messages: 完整历史或 AG-UI 消息快照。
 *   user_message_id: 本轮用户消息 ID，防止起始快照串入上一轮。
 */
export function mergeAssistantProcessSnapshot(
  message: Message,
  state_messages: unknown,
  user_message_id: string | undefined
): Message {
  if (!user_message_id) return message
  const history = toHistoryMessages(state_messages)
  const user_index = history.findLastIndex((item) => item.role === 'user')
  if (user_index < 0 || history[user_index].id !== user_message_id) return message
  const snapshot = history[user_index + 1]
  if (!snapshot || snapshot.role !== 'ai') return message

  const next = { ...message, messageItems: [...(message.messageItems || [])] }
  const live_reasoning = message.reasoningContent || ''
  const snapshot_reasoning = snapshot.reasoningContent || ''
  if (snapshot_reasoning && !live_reasoning && !message.reasoningBlocks?.length) {
    next.reasoningContent = snapshot_reasoning
    next.reasoningBlocks = snapshot.reasoningBlocks
    next.messageItems.push(...(snapshot.messageItems || []).filter((item) => item.type === 'reasoning'))
  } else if (live_reasoning && snapshot_reasoning.startsWith(live_reasoning) && snapshot_reasoning.length > live_reasoning.length) {
    const blocks = message.reasoningBlocks || [{ id: `${message.id}_reasoning_legacy`, content: live_reasoning }]
    next.reasoningContent = snapshot_reasoning
    next.reasoningBlocks = blocks.map((block, index) => index === blocks.length - 1
      ? { ...block, content: block.content + snapshot_reasoning.slice(live_reasoning.length) }
      : block)
  }
  next.toolData = [...(message.toolData || [])]
  for (const tool of snapshot.toolData || []) {
    const index = next.toolData.findIndex((item) => item.toolCall.id === tool.toolCall.id)
    if (index < 0) {
      next.toolData.push(tool)
      next.messageItems = ensureToolItem(next.messageItems, tool.toolCall.id)
    } else {
      const live = next.toolData[index]
      next.toolData[index] = {
        ...tool, ...live,
        toolCall: { ...tool.toolCall, ...live.toolCall,
          name: live.toolCall.name === 'tool' ? tool.toolCall.name : live.toolCall.name,
          args: Object.keys(live.toolCall.args).length ? live.toolCall.args : tool.toolCall.args },
        toolOutput: live.toolOutput?.some((output) => output.kind !== 'decision')
          ? live.toolOutput
          : [...(live.toolOutput || []), ...(tool.toolOutput || [])],
      }
    }
  }
  return next
}

/**
 * 将人工审批决定记录在对应工具的输出中，保留同名工具的历史执行记录。
 *
 * Args:
 *   message: 当前 assistant 消息。
 *   actions: 本次待审批的工具请求。
 *   decisions: 按请求顺序排列的审批决定。
 */
export function recordToolDecisions(
  message: Message,
  actions: InterruptData['action_requests'],
  decisions: ResumeDecision[]
): Message {
  const tools = [...(message.toolData || [])]
  const matched = new Set<number>()
  actions.forEach((action, action_index) => {
    const decision = decisions[action_index]
    if (!decision) return
    const index = tools.findLastIndex((tool, tool_index) =>
      !matched.has(tool_index) && tool.toolCall.name === action.name &&
      !tool.toolOutput?.some((output) => output.kind !== 'decision')
    )
    if (index < 0) return
    matched.add(index)
    const tool = tools[index]
    const status = decision.type === 'reject' ? 'rejected'
      : decision.type === 'edit' ? 'edited' : 'approved'
    const content = decision.type === 'reject' ? decision.message || '用户已拒绝执行。'
      : decision.type === 'edit' ? `用户已修改参数并批准执行：${JSON.stringify(decision.edited_action.args)}`
        : decision.type === 'respond' ? decision.message : '用户已批准执行。'
    tools[index] = {
      ...tool,
      approvalStatus: status,
      toolCall: decision.type === 'edit'
        ? { ...tool.toolCall, name: decision.edited_action.name, args: decision.edited_action.args }
        : tool.toolCall,
      toolOutput: [
        ...(tool.toolOutput || []).filter((output) => output.kind !== 'decision'),
        { tool_call_id: tool.toolCall.id, content, kind: 'decision' },
      ],
    }
  })
  return { ...message, toolData: tools }
}

/**
 * 恢复原 assistant 消息并继续浏览器计时，排除等待人工输入的时间。
 *
 * Args:
 *   message: 待恢复的 assistant 消息。
 *   now: 浏览器开始恢复请求的时间。
 */
export function resumeAssistantMessage(message: Message, now: number): Message {
  return {
    ...message,
    startedAt: now - (message.duration || 0),
    duration: undefined,
    error: undefined,
  }
}

export function appendReasoningToken(
  blocks: ReasoningBlock[] | undefined,
  items: AssistantMessageItem[] | undefined,
  token: string,
  startNewBlock: boolean,
  createBlockId: () => string,
  legacyContent?: string
): { reasoningBlocks: ReasoningBlock[]; messageItems: AssistantMessageItem[] } {
  const normalizedBlocks =
    blocks && blocks.length > 0
      ? blocks
      : legacyContent
        ? [{ id: createBlockId(), content: legacyContent }]
        : []
  const normalizedItems =
    items && items.length > 0
      ? items
      : normalizedBlocks.map((block) => ({
          id: `reasoning_item_${block.id}`,
          type: 'reasoning' as const,
          reasoningBlockId: block.id,
        }))

  if (startNewBlock || normalizedBlocks.length === 0) {
    const id = createBlockId()
    return {
      reasoningBlocks: [...normalizedBlocks, { id, content: token }],
      messageItems: [
        ...normalizedItems,
        {
          id: `reasoning_item_${id}`,
          type: 'reasoning',
          reasoningBlockId: id,
        },
      ],
    }
  }

  return {
    reasoningBlocks: normalizedBlocks.map((block, index) =>
      index === normalizedBlocks.length - 1
        ? { ...block, content: `${block.content}${token}` }
        : block
    ),
    messageItems: normalizedItems,
  }
}

export function appendContentToken(
  blocks: ReasoningBlock[] | undefined,
  items: AssistantMessageItem[] | undefined,
  token: string,
  appendToLastBlock: boolean,
  createBlockId: () => string
): { contentBlocks: ReasoningBlock[]; messageItems: AssistantMessageItem[] } {
  const normalizedBlocks = blocks || []
  const normalizedItems = items || []

  if (appendToLastBlock && normalizedBlocks.length > 0) {
    return {
      contentBlocks: normalizedBlocks.map((block, index) =>
        index === normalizedBlocks.length - 1
          ? { ...block, content: `${block.content}${token}` }
          : block
      ),
      messageItems: normalizedItems,
    }
  }

  const id = createBlockId()
  return {
    contentBlocks: [...normalizedBlocks, { id, content: token }],
    messageItems: [
      ...normalizedItems,
      {
        id: `content_item_${id}`,
        type: 'content',
        contentBlockId: id,
      },
    ],
  }
}

export function ensureToolItem(
  items: AssistantMessageItem[] | undefined,
  toolCallId: string
): AssistantMessageItem[] {
  const normalizedItems = items || []
  if (
    normalizedItems.some(
      (item) => item.type === 'tool' && item.toolCallId === toolCallId
    )
  ) {
    return normalizedItems
  }

  return [
    ...normalizedItems,
    {
      id: `tool_item_${toolCallId}`,
      type: 'tool',
      toolCallId,
    },
  ]
}

export type ResumeDecision =
  | { type: 'approve' }
  | { type: 'respond'; message: string }
  | { type: 'reject'; message: string }
  | {
      type: 'edit'
      edited_action: {
        name: string
        args: Record<string, unknown>
      }
}
