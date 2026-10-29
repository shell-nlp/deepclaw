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
        'text' in item &&
        typeof item.text === 'string'
      ) {
        return item.text
      }
      return ''
    })
    .join('')
}

function getHistoryReasoningContent(message: Record<string, unknown>): string {
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
  return ''
}

function getHistoryToolData(message: Record<string, unknown>): ToolData[] {
  if (!Array.isArray(message.tool_calls)) return []

  return message.tool_calls.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const toolCall = item as Record<string, unknown>
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
    if (message.type === 'human') {
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

    if (message.type === 'ai') {
      if (!activeAssistant) {
        activeAssistant = createHistoryAssistantMessage(
          `${messageId}_assistant`,
          createdAt
        )
        historyMessages.push(activeAssistant)
      }
      const reasoningContent = getHistoryReasoningContent(message)
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
      if (content) {
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

    if (message.type !== 'tool' || typeof message.tool_call_id !== 'string') return

    const toolCallId = message.tool_call_id
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
    tool.toolOutput?.push(toolOutput)
  })

  return historyMessages
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
  | { type: 'reject'; message: string }
  | {
      type: 'edit'
      edited_action: {
        name: string
        args: Record<string, unknown>
      }
}
