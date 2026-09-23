'use client'

import {
  ChangeEvent,
  KeyboardEvent,
  MouseEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'

import styles from './ChatInterface.module.css'
import {
  buildAuthorizationHeaders,
  clearStoredAuthToken,
  fetchCurrentActor,
  getActorCapabilities,
  getStoredAuthToken,
  GUEST_USER_ID,
  isUnauthorizedErrorMessage,
  normalizeActorPayload,
  revokeAuthToken,
  type ActorState,
} from './chat-interface/auth'
import {
  createAgUiRunInput,
  getAgUiInterrupt,
  getAgUiInterruptOutcome,
  getAgUiAssistantSnapshotText,
  getRecommendedQuestions,
  parseAgUiSseFrame,
  type AgUiEvent,
  type AgUiInterrupt,
} from './chat-interface/agui'
import { resolveChannelEntryPage } from './chat-interface/channelManagement'
import { ChannelManagementView } from './chat/management/ChannelManagementView'
import { ChatView } from './chat-interface/ChatView'
import { AppSidebar } from './chat/shared/AppSidebar'
import {
  AGUI_AGENTS_API_PATH,
  AGUI_THREAD_RUNS_API_PATH,
  AGUI_THREADS_API_PATH,
  AGUI_THREAD_DELETE_API_PATH,
  AGUI_THREAD_STATE_API_PATH,
  AUTH_USERS_CREATE_API_PATH,
  AUTH_USERS_LIST_API_PATH,
  AUTH_USERS_RESET_PASSWORD_API_PATH,
  AUTH_USERS_UPDATE_ROLE_API_PATH,
  AUTH_USERS_UPDATE_STATUS_API_PATH,
  DEFAULT_AGUI_API_PATH,
  DEFAULT_CHANNEL_PAGE,
  DEFAULT_KNOWLEDGE_PAGE,
  DEFAULT_MCP_CONFIG_TEMPLATE,
  RUNTIME_CONFIG_API_PATH,
  DOCUMENT_CHUNK_PAGE_SIZE,
  DOCUMENT_PAGE_SIZE,
  KB_BULK_DELETE_API_PATH,
  KB_CREATE_API_PATH,
  KB_DELETE_API_PATH,
  KB_DETAIL_API_PATH,
  KB_DOCUMENT_BULK_DELETE_API_PATH,
  KB_DOCUMENT_DELETE_API_PATH,
  KB_DOCUMENT_DETAIL_API_PATH,
  KB_DOCUMENT_LIST_API_PATH,
  KB_DOCUMENT_UPDATE_API_PATH,
  KB_DOCUMENT_UPLOAD_API_PATH,
  KB_LIST_API_PATH,
  KB_UPDATE_API_PATH,
  KNOWLEDGE_BASE_PAGE_SIZE,
  SKILL_DELETE_API_PATH,
  SKILL_LIST_API_PATH,
  SKILL_UPLOAD_API_PATH,
} from './chat-interface/constants'
import { KnowledgeManagementView } from './chat/management/KnowledgeManagementView'
import { McpManagementView } from './chat/management/McpManagementView'
import { SkillManagementView } from './chat/management/SkillManagementView'
import type {
  AssistantMessageItem,
  AgentListResponse,
  AgentSummary,
  ChannelManagementPage,
  AuthLoginResponse,
  ThreadListResponse,
  ChatHistorySession,
  AuthUserListResponse,
  AuthUserSummary,
  BulkDeleteDocumentResponse,
  BulkDeleteKnowledgeBaseResponse,
  ChatError,
  ChatErrorKind,
  ChatStatus,
  InterruptData,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeDocumentDetailResponse,
  KnowledgePage,
  Message,
  PaginatedKnowledgeBaseResponse,
  PaginatedKnowledgeDocumentResponse,
  RequestMode,
  ReasoningBlock,
  SkillDeleteResponse,
  SkillListResponse,
  SkillRecord,
  SkillUploadResponse,
  ThreadRunListResponse,
  ToolData,
  UploadResult,
  ViewMode,
} from './chat-interface/types'
import { UserManagementView } from './chat/management/UserManagementView'
import {
  fetchJson,
  generateMessageId,
  generateSessionId,
  getApiUrl,
  getPageTotal,
  getRouteHash,
  parseRouteHash,
  parseMcpConfig,
  stringifyToolContent,
} from './chat-interface/utils'

type AssistantStreamKind = 'reasoning' | 'content' | 'tool' | 'interrupt' | null

type ThreadRuntime = {
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

function createThreadRuntime(threadId: string): ThreadRuntime {
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

function isActiveRunStatus(status: string): boolean {
  return status === 'queued' || status === 'running' || status === 'cancelling'
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  )
}

class ChatRequestError extends Error {
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

function createChatError(
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

async function createHttpChatError(
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

function toChatError(error: unknown, fallbackKind: ChatErrorKind = 'unknown'): ChatError {
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

function toHistoryMessages(
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

function appendReasoningToken(
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

function appendContentToken(
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

function ensureToolItem(
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

type ResumeDecision =
  | { type: 'approve' }
  | { type: 'reject'; message: string }
  | {
      type: 'edit'
      edited_action: {
        name: string
        args: Record<string, unknown>
      }
}

export default function ChatInterface() {
  const [viewMode, setViewMode] = useState<ViewMode>('chat')
  const [channelPage, setChannelPage] =
    useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
  const [lastChannelPage, setLastChannelPage] =
    useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
  const [channelNavExpanded, setChannelNavExpanded] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [knowledgePage, setKnowledgePage] =
    useState<KnowledgePage>(DEFAULT_KNOWLEDGE_PAGE)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [historySessions, setHistorySessions] = useState<ChatHistorySession[]>([])
  const [historyExpanded, setHistoryExpanded] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoadingSessionId, setHistoryLoadingSessionId] = useState<string | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [status, setStatus] = useState<'ready' | 'connecting' | 'error'>('ready')
  const [aguiApiPath, setAguiApiPath] = useState(DEFAULT_AGUI_API_PATH)
  const [availableAgents, setAvailableAgents] = useState<AgentSummary[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [runningThreadIds, setRunningThreadIds] = useState<string[]>([])
  const [internetSearch, setInternetSearch] = useState(false)
  const [deepThinking, setDeepThinking] = useState(true)
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(false)
  const [showInterrupt, setShowInterrupt] = useState(false)
  const [interruptData, setInterruptData] = useState<InterruptData | null>(null)
  const [toolCallDurations, setToolCallDurations] = useState<Record<string, number>>({})

  const [actor, setActor] = useState<ActorState>(() => normalizeActorPayload(null))
  const [authToken, setAuthToken] = useState('')
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const [adminUsers, setAdminUsers] = useState<AuthUserSummary[]>([])
  const [loadingAdminUsers, setLoadingAdminUsers] = useState(false)
  const [userAdminNotice, setUserAdminNotice] = useState('')
  const [userAdminError, setUserAdminError] = useState('')

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [knowledgeBaseTotal, setKnowledgeBaseTotal] = useState(0)
  const [knowledgeBasePage, setKnowledgeBasePage] = useState(1)
  const [knowledgeBaseSearchInput, setKnowledgeBaseSearchInput] = useState('')
  const [knowledgeBaseSearch, setKnowledgeBaseSearch] = useState('')

  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState('')
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] =
    useState<KnowledgeBase | null>(null)
  const [checkedKnowledgeBaseIds, setCheckedKnowledgeBaseIds] = useState<string[]>([])

  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [documentTotal, setDocumentTotal] = useState(0)
  const [documentPage, setDocumentPage] = useState(1)
  const [documentSearchInput, setDocumentSearchInput] = useState('')
  const [documentSearch, setDocumentSearch] = useState('')
  const [checkedDocumentIds, setCheckedDocumentIds] = useState<string[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [selectedDocumentDetail, setSelectedDocumentDetail] =
    useState<KnowledgeDocumentDetailResponse | null>(null)
  const [documentChunkPage, setDocumentChunkPage] = useState(1)
  const [loadingDocumentDetail, setLoadingDocumentDetail] = useState(false)

  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [showCreateKnowledgeBaseModal, setShowCreateKnowledgeBaseModal] =
    useState(false)

  const [mcpConfigDraft, setMcpConfigDraft] = useState('')
  const [savedMcpConfigText, setSavedMcpConfigText] = useState('')
  const [mcpConfig, setMcpConfig] = useState<Record<string, unknown> | null>(null)
  const [mcpEnabled, setMcpEnabled] = useState(false)
  const [mcpNotice, setMcpNotice] = useState('')
  const [mcpError, setMcpError] = useState('')

  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [loadingSkills, setLoadingSkills] = useState(false)
  const [uploadingSkills, setUploadingSkills] = useState(false)
  const [skillNotice, setSkillNotice] = useState('')
  const [skillError, setSkillError] = useState('')

  const [managementError, setManagementError] = useState('')
  const [managementNotice, setManagementNotice] = useState('')
  const [loadingKnowledgeBases, setLoadingKnowledgeBases] = useState(false)
  const [loadingDocuments, setLoadingDocuments] = useState(false)
  const [savingKnowledgeBase, setSavingKnowledgeBase] = useState(false)
  const [uploadingDocuments, setUploadingDocuments] = useState(false)
  const [deletingBulk, setDeletingBulk] = useState(false)

  const chatContainerRef = useRef<HTMLDivElement>(null)
  const isChatAtBottomRef = useRef(true)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const skillUploadInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const activeThreadIdRef = useRef('')
  const threadRuntimesRef = useRef<Map<string, ThreadRuntime>>(new Map())
  const messagesRef = useRef<Message[]>([])
  const streamGenerationRef = useRef(0)
  const switchToThreadRef = useRef<(threadId: string) => Promise<void>>(
    async () => undefined
  )
  const currentRunIdRef = useRef<string | null>(null)
  const currentRunInputRef = useRef<Record<string, unknown> | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const toolCallArgsRef = useRef<Record<string, string>>({})
  const currentAssistantMessageIdRef = useRef<string | null>(null)
  const processedToolCallIdsRef = useRef<Set<string>>(new Set())
  const lastAssistantStreamEventRef = useRef<
    'reasoning' | 'content' | 'tool' | 'interrupt' | null
  >(null)
  const reasoningStartTimeRef = useRef<number | null>(null)
  const toolCallStartTimesRef = useRef<Record<string, number>>({})
  const reasoningBlockCounterRef = useRef(0)
  const contentBlockCounterRef = useRef(0)
  const requestModeRef = useRef<RequestMode>('agent')
  const requestKnowledgeBaseRef = useRef<KnowledgeBase | null>(null)
  const requestMcpConfigRef = useRef<Record<string, unknown> | null>(null)
  const retryActionsRef = useRef<Map<string, () => void | Promise<void>>>(
    new Map()
  )

  const setMessagesAndRef = useCallback(
    (updater: Message[] | ((prev: Message[]) => Message[])) => {
      setMessages((prev) => {
        const next =
          typeof updater === 'function'
            ? (updater as (current: Message[]) => Message[])(prev)
            : updater
        messagesRef.current = next
        return next
      })
    },
    []
  )

  const setThreadRunning = useCallback((threadId: string, running: boolean) => {
    setRunningThreadIds((prev) => {
      if (running) {
        return prev.includes(threadId) ? prev : [...prev, threadId]
      }
      return prev.filter((item) => item !== threadId)
    })
  }, [])

  const getThreadRuntime = useCallback((threadId: string): ThreadRuntime => {
    const existing = threadRuntimesRef.current.get(threadId)
    if (existing) return existing
    const runtime = createThreadRuntime(threadId)
    threadRuntimesRef.current.set(threadId, runtime)
    return runtime
  }, [])

  const syncRuntimeToRefs = useCallback((runtime: ThreadRuntime) => {
    currentRunIdRef.current = runtime.runId
    currentRunInputRef.current = runtime.runInput
    lastEventIdRef.current = runtime.lastEventId
    currentAssistantMessageIdRef.current = runtime.assistantMessageId
    processedToolCallIdsRef.current = new Set(runtime.processedToolCallIds)
    lastAssistantStreamEventRef.current = runtime.lastAssistantStreamEvent
    reasoningStartTimeRef.current = runtime.reasoningStartTime
    toolCallStartTimesRef.current = { ...runtime.toolCallStartTimes }
    toolCallArgsRef.current = { ...runtime.toolCallArgs }
    reasoningBlockCounterRef.current = runtime.reasoningBlockCounter
    contentBlockCounterRef.current = runtime.contentBlockCounter
    requestModeRef.current = runtime.requestMode
    requestKnowledgeBaseRef.current = runtime.requestKnowledgeBase
    requestMcpConfigRef.current = runtime.requestMcpConfig
    abortControllerRef.current = runtime.abortController
  }, [])

  const syncRuntimeToView = useCallback(
    (runtime: ThreadRuntime) => {
      activeThreadIdRef.current = runtime.threadId
      messagesRef.current = runtime.messages
      setSessionId(runtime.threadId)
      setMessagesAndRef(runtime.messages)
      setStatus(runtime.status)
      setIsProcessing(runtime.processing)
      setShowInterrupt(runtime.showInterrupt)
      setInterruptData(runtime.interruptData)
      setToolCallDurations(runtime.toolCallDurations)
      syncRuntimeToRefs(runtime)
      if (typeof window !== 'undefined') {
        localStorage.setItem('rag_chat_session_id', runtime.threadId)
      }
    },
    [setMessagesAndRef, syncRuntimeToRefs]
  )

  const persistActiveRuntime = useCallback((): ThreadRuntime | null => {
    const threadId = activeThreadIdRef.current
    if (!threadId) return null
    const runtime = getThreadRuntime(threadId)
    runtime.messages = messagesRef.current
    runtime.runId = currentRunIdRef.current
    runtime.runInput = currentRunInputRef.current
    runtime.lastEventId = lastEventIdRef.current
    runtime.showInterrupt = showInterrupt
    runtime.interruptData = interruptData
    runtime.toolCallDurations = toolCallDurations
    runtime.assistantMessageId = currentAssistantMessageIdRef.current
    runtime.processedToolCallIds = Array.from(processedToolCallIdsRef.current)
    runtime.lastAssistantStreamEvent = lastAssistantStreamEventRef.current
    runtime.reasoningStartTime = reasoningStartTimeRef.current
    runtime.toolCallStartTimes = { ...toolCallStartTimesRef.current }
    runtime.toolCallArgs = { ...toolCallArgsRef.current }
    runtime.reasoningBlockCounter = reasoningBlockCounterRef.current
    runtime.contentBlockCounter = contentBlockCounterRef.current
    runtime.requestMode = requestModeRef.current
    runtime.requestKnowledgeBase = requestKnowledgeBaseRef.current
    runtime.requestMcpConfig = requestMcpConfigRef.current
    runtime.abortController = abortControllerRef.current
    return runtime
  }, [
    getThreadRuntime,
    interruptData,
    showInterrupt,
    toolCallDurations,
  ])

  const resetActiveChatView = useCallback(
    (nextSessionId: string) => {
      activeThreadIdRef.current = nextSessionId
      messagesRef.current = []
      setSessionId(nextSessionId)
      setMessagesAndRef([])
      setShowInterrupt(false)
      setInterruptData(null)
      setToolCallDurations({})
      setStatus('ready')
      setIsProcessing(false)
      currentRunIdRef.current = null
      currentRunInputRef.current = null
      lastEventIdRef.current = null
      currentAssistantMessageIdRef.current = null
      processedToolCallIdsRef.current.clear()
      lastAssistantStreamEventRef.current = null
      reasoningStartTimeRef.current = null
      toolCallStartTimesRef.current = {}
      toolCallArgsRef.current = {}
      reasoningBlockCounterRef.current = 0
      contentBlockCounterRef.current = 0
      requestModeRef.current = 'agent'
      requestKnowledgeBaseRef.current = null
      requestMcpConfigRef.current = null
      abortControllerRef.current = null
      isChatAtBottomRef.current = true
      if (typeof window !== 'undefined') {
        localStorage.setItem('rag_chat_session_id', nextSessionId)
      }
    },
    [setMessagesAndRef]
  )

  const actorCapabilities = getActorCapabilities(actor)
  const currentUserId = actor.userId || GUEST_USER_ID
  const mcpDraftParseResult = parseMcpConfig(mcpConfigDraft)
  const savedMcpParseResult = parseMcpConfig(savedMcpConfigText)
  const mcpConfigDirty = mcpConfigDraft !== savedMcpConfigText

  const scrollToBottom = useCallback(() => {
    if (chatContainerRef.current && isChatAtBottomRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [])

  /**
   * 记录用户是否仍停留在聊天记录底部附近，以决定是否继续自动滚动。
   *
   * Args:
   * - 无。
   */
  const handleChatScroll = useCallback(() => {
    const container = chatContainerRef.current
    if (!container) return

    const distanceToBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight
    isChatAtBottomRef.current = distanceToBottom <= 24
  }, [])

  const clearChat = useCallback(() => {
    const previousRuntime = persistActiveRuntime()
    streamGenerationRef.current += 1
    previousRuntime?.abortController?.abort()
    if (previousRuntime) {
      previousRuntime.abortController = null
    }
    abortControllerRef.current = null

    const nextSessionId = generateSessionId()
    resetActiveChatView(nextSessionId)
    getThreadRuntime(nextSessionId)
    setThreadRunning(nextSessionId, false)
  }, [
    getThreadRuntime,
    persistActiveRuntime,
    resetActiveChatView,
    setThreadRunning,
  ])

  const resetAllRuntimesAndChat = useCallback(() => {
    streamGenerationRef.current += 1
    abortControllerRef.current?.abort()
    threadRuntimesRef.current.forEach((runtime) => runtime.abortController?.abort())
    threadRuntimesRef.current.clear()
    setRunningThreadIds([])
    const nextSessionId = generateSessionId()
    resetActiveChatView(nextSessionId)
    getThreadRuntime(nextSessionId)
  }, [getThreadRuntime, resetActiveChatView])

  const resetUserScopedState = useCallback(() => {
    setKnowledgeBasePage(1)
    setKnowledgeBaseSearch('')
    setKnowledgeBaseSearchInput('')
    setSelectedKnowledgeBaseId('')
    setSelectedKnowledgeBase(null)
    setCheckedKnowledgeBaseIds([])
    setKnowledgeBases([])
    setKnowledgeBaseTotal(0)

    setDocumentPage(1)
    setDocumentSearch('')
    setDocumentSearchInput('')
    setCheckedDocumentIds([])
    setDocuments([])
    setDocumentTotal(0)
    setSelectedDocumentId('')
    setSelectedDocumentDetail(null)
    setDocumentChunkPage(1)

    setAdminUsers([])
    resetAllRuntimesAndChat()
  }, [resetAllRuntimesAndChat])

  const applyActorState = useCallback(
    (nextActor: ActorState) => {
      setActor(nextActor)
      resetUserScopedState()
    },
    [resetUserScopedState]
  )

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
    [applyActorState]
  )

  const withAuthHeaders = useCallback(
    (headers?: HeadersInit) => ({
      ...(headers || {}),
      ...buildAuthorizationHeaders(authToken),
    }),
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
        if (error instanceof Error && isUnauthorizedErrorMessage(error.message)) {
          clearAuthState('登录状态已失效，已切换为游客模式。')
        }
        throw error
      }
    },
    [clearAuthState, withAuthHeaders]
  )

  const addMessage = useCallback((message: Message) => {
    setMessagesAndRef((prev) => {
      const existing = prev.find((item) => item.id === message.id)
      if (existing) {
        return prev.map((item) =>
          item.id === message.id ? { ...item, ...message } : item
        )
      }
      return [...prev, message]
    })
  }, [setMessagesAndRef])

  const ensureAssistantMessage = useCallback(() => {
    let assistantMessageId = currentAssistantMessageIdRef.current
    if (!assistantMessageId) {
      assistantMessageId = generateMessageId()
      currentAssistantMessageIdRef.current = assistantMessageId
      addMessage({
        id: assistantMessageId,
        role: 'ai',
        content: '',
        createdAt: Date.now(),
        toolData: [],
        startedAt: Date.now(),
      })
    }
    return assistantMessageId
  }, [addMessage])

  const updateAssistantMessage = useCallback(
    (updater: (message: Message) => Message) => {
      const assistantMessageId = ensureAssistantMessage()
      setMessagesAndRef((prev) =>
        prev.map((item) => (item.id === assistantMessageId ? updater(item) : item))
      )
    },
    [ensureAssistantMessage, setMessagesAndRef]
  )

  const applyAssistantError = useCallback(
    (messageId: string | null, error: unknown) => {
      const targetId = messageId ?? currentAssistantMessageIdRef.current
      if (!targetId) return
      const chatError = toChatError(error)
      const finishedAt = Date.now()
      setMessagesAndRef((prev) =>
        prev.map((message) => {
          if (message.id !== targetId) return message
          return {
            ...message,
            error: chatError,
            duration:
              message.duration ??
              (message.startedAt !== undefined
                ? Math.max(0, finishedAt - message.startedAt)
                : undefined),
          }
        })
      )
    },
    [setMessagesAndRef]
  )

  const registerRetryAction = useCallback(
    (messageId: string, action: () => void | Promise<void>) => {
      retryActionsRef.current.set(messageId, action)
    },
    []
  )

  const handleRetryMessage = useCallback(
    async (messageId: string) => {
      const action = retryActionsRef.current.get(messageId)
      if (!action) return
      retryActionsRef.current.delete(messageId)
      setMessagesAndRef((prev) =>
        prev.map((message) =>
          message.id === messageId ? { ...message, error: undefined } : message
        )
      )
      await action()
    },
    [setMessagesAndRef]
  )

  useEffect(() => {
    if (typeof window === 'undefined') return

    const freshSessionId = generateSessionId()
    const storedMcpConfig = localStorage.getItem('rag_mcp_config') || ''
    const storedMcpEnabled = localStorage.getItem('rag_mcp_enabled') === 'true'
    const parsedMcpConfig = parseMcpConfig(storedMcpConfig)

    localStorage.setItem('rag_chat_session_id', freshSessionId)
    localStorage.setItem(
      'rag_mcp_enabled',
      parsedMcpConfig.config && storedMcpEnabled ? 'true' : 'false'
    )

    activeThreadIdRef.current = freshSessionId
    messagesRef.current = []
    setSessionId(freshSessionId)
    getThreadRuntime(freshSessionId)
    setMcpConfigDraft(storedMcpConfig)
    setSavedMcpConfigText(storedMcpConfig)
    setMcpConfig(parsedMcpConfig.config)
    setMcpEnabled(Boolean(parsedMcpConfig.config) && storedMcpEnabled)

    if (storedMcpConfig && parsedMcpConfig.error) {
      setMcpError(`本地保存的 MCP 配置无效：${parsedMcpConfig.error}`)
    }

    // 按后端 runtime-config 获取统一 AG-UI 路径与可用智能体
    void fetch(getApiUrl(RUNTIME_CONFIG_API_PATH))
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`runtime-config HTTP ${response.status}`)
        }
        return (await response.json()) as {
          agui_runs_path?: string
        }
      })
      .then((config) => {
        if (config.agui_runs_path) {
          setAguiApiPath(config.agui_runs_path)
        }
      })
      .catch(() => {
        // 拉取失败时回退默认统一路径，避免阻塞聊天
        setAguiApiPath(DEFAULT_AGUI_API_PATH)
      })

    void fetch(getApiUrl(AGUI_AGENTS_API_PATH))
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`agents HTTP ${response.status}`)
        }
        return (await response.json()) as AgentListResponse
      })
      .then((response) => setAvailableAgents(response.items))
      .catch(() => setAvailableAgents([]))

    const storedToken = getStoredAuthToken()
    if (!storedToken) return

    setAuthToken(storedToken)
    void fetchCurrentActor(storedToken)
      .then((nextActor) => {
        applyActorState(nextActor)
      })
      .catch(() => {
        clearAuthState('登录状态已失效，已切换为游客模式。')
      })
  }, [applyActorState, clearAuthState, getThreadRuntime])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const navigateTo = useCallback(
    (
      nextViewMode: ViewMode,
      nextKnowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE,
      nextChannelPage: ChannelManagementPage = channelPage,
      replace = false
    ) => {
      const safeKnowledgePage =
        (
          nextKnowledgePage === 'library-detail' ||
          nextKnowledgePage === 'document-detail'
        ) &&
        !selectedKnowledgeBase
          ? 'libraries'
          : nextKnowledgePage

      setViewMode(nextViewMode)
      setKnowledgePage(safeKnowledgePage)
      setChannelPage(nextChannelPage)
      if (nextViewMode === 'channels') {
        setLastChannelPage(nextChannelPage)
        setChannelNavExpanded(true)
      }

      if (typeof window === 'undefined') return
      const nextHash = getRouteHash(nextViewMode, safeKnowledgePage, nextChannelPage)
      if (window.location.hash === nextHash) return

      if (replace) {
        window.history.replaceState(null, '', nextHash)
      } else {
        window.history.pushState(null, '', nextHash)
      }
    },
    [selectedKnowledgeBase]
  )

  const loadHistorySessions = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const response = await requestJson<ThreadListResponse>(AGUI_THREADS_API_PATH)
      setHistorySessions(
        response.items.map((thread) => ({
          session_id: thread.threadId,
          agent_id: thread.agentId,
          updated_at: new Date(thread.updatedAt * 1000).toISOString(),
          title: thread.title,
        }))
      )
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : '获取聊天历史失败。')
    } finally {
      setHistoryLoading(false)
    }
  }, [requestJson])

  const openHistorySession = useCallback(
    async (targetSessionId: string) => {
      if (targetSessionId === sessionId) return

      setHistoryLoadingSessionId(targetSessionId)
      setHistoryError('')
      try {
        await switchToThreadRef.current(targetSessionId)
        navigateTo('chat')
        requestAnimationFrame(scrollToBottom)
      } catch (error) {
        setHistoryError(error instanceof Error ? error.message : '加载聊天历史失败。')
      } finally {
        setHistoryLoadingSessionId(null)
      }
    },
    [navigateTo, scrollToBottom, sessionId]
  )

  const deleteHistorySession = useCallback(
    async (targetSessionId: string, event: MouseEvent<HTMLButtonElement>) => {
      event.stopPropagation()
      if (runningThreadIds.includes(targetSessionId)) return

      setHistoryLoadingSessionId(targetSessionId)
      setHistoryError('')
      try {
        await requestJson<{ threadId: string; deleted: boolean }>(
          AGUI_THREAD_DELETE_API_PATH(targetSessionId),
          { method: 'DELETE' }
        )

        setHistorySessions((sessions) =>
          sessions.filter((session) => session.session_id !== targetSessionId)
        )
        const runtime = threadRuntimesRef.current.get(targetSessionId)
        runtime?.abortController?.abort()
        threadRuntimesRef.current.delete(targetSessionId)
        setThreadRunning(targetSessionId, false)
        if (targetSessionId === sessionId) {
          streamGenerationRef.current += 1
          abortControllerRef.current?.abort()
          abortControllerRef.current = null
          const nextSessionId = generateSessionId()
          resetActiveChatView(nextSessionId)
          getThreadRuntime(nextSessionId)
          setThreadRunning(nextSessionId, false)
        }
      } catch (error) {
        setHistoryError(error instanceof Error ? error.message : '删除聊天历史失败。')
      } finally {
        setHistoryLoadingSessionId(null)
      }
    },
    [
      getThreadRuntime,
      requestJson,
      resetActiveChatView,
      runningThreadIds,
      sessionId,
      setThreadRunning,
    ]
  )

  useEffect(() => {
    void loadHistorySessions()
  }, [loadHistorySessions])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const syncRoute = () => {
      const route = parseRouteHash(window.location.hash)
      const safeKnowledgePage =
        (
          route.knowledgePage === 'library-detail' ||
          route.knowledgePage === 'document-detail'
        ) &&
        !selectedKnowledgeBase
          ? 'libraries'
          : route.knowledgePage

      setViewMode(route.viewMode)
      setKnowledgePage(safeKnowledgePage)
      setChannelPage(route.channelPage)
      if (route.viewMode === 'channels') {
        setLastChannelPage(route.channelPage)
        setChannelNavExpanded(true)
      }

      const expectedHash = getRouteHash(
        route.viewMode,
        safeKnowledgePage,
        route.channelPage
      )
      if (window.location.hash !== expectedHash) {
        window.history.replaceState(null, '', expectedHash)
      }
    }

    if (!window.location.hash) {
      window.history.replaceState(
        null,
        '',
        getRouteHash('chat', DEFAULT_KNOWLEDGE_PAGE, DEFAULT_CHANNEL_PAGE)
      )
    }

    syncRoute()
    window.addEventListener('hashchange', syncRoute)
    return () => window.removeEventListener('hashchange', syncRoute)
  }, [selectedKnowledgeBase])

  const handleChannelsNavClick = useCallback(() => {
    if (viewMode !== 'channels') {
      const nextPage = resolveChannelEntryPage(undefined, lastChannelPage)
      navigateTo('channels', DEFAULT_KNOWLEDGE_PAGE, nextPage)
      return
    }

    setChannelNavExpanded((current) => !current)
  }, [lastChannelPage, navigateTo, viewMode])

  /**
   * 切换侧边导航的展开状态，为聊天主区域腾出更多空间。
   *
   * Args:
   * - 无。
   */
  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((collapsed) => !collapsed)
  }, [])

  const navigateToKnowledgeView = useCallback(
    (
      nextViewMode: ViewMode,
      nextKnowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE,
      replace = false
    ) => {
      navigateTo(nextViewMode, nextKnowledgePage, channelPage, replace)
    },
    [channelPage, navigateTo]
  )

  useEffect(() => {
    scrollToBottom()
  }, [messages, showInterrupt, interruptData, scrollToBottom])

  const loadKnowledgeBases = useCallback(
    async (page = knowledgeBasePage, search = knowledgeBaseSearch) => {
      setLoadingKnowledgeBases(true)
      setManagementError('')
      try {
        const result = await requestJson<PaginatedKnowledgeBaseResponse>(
          KB_LIST_API_PATH,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: currentUserId,
              search,
              page,
              page_size: KNOWLEDGE_BASE_PAGE_SIZE,
            }),
          }
        )
        setKnowledgeBases(result.items)
        setKnowledgeBaseTotal(result.total)

        if (selectedKnowledgeBaseId) {
          const matched = result.items.find(
            (item) => item.knowledge_base_id === selectedKnowledgeBaseId
          )
          if (matched) {
            setSelectedKnowledgeBase(matched)
          } else {
            setSelectedKnowledgeBaseId('')
            setSelectedKnowledgeBase(null)
          }
        }
      } catch (error) {
        setManagementError(error instanceof Error ? error.message : '加载知识库失败。')
        setKnowledgeBases([])
        setKnowledgeBaseTotal(0)
      } finally {
        setLoadingKnowledgeBases(false)
      }
    },
    [currentUserId, knowledgeBasePage, knowledgeBaseSearch, requestJson, selectedKnowledgeBaseId]
  )

  const loadKnowledgeBaseDetail = useCallback(
    async (knowledgeBaseId: string) => {
      if (!knowledgeBaseId) return
      setManagementError('')
      try {
        const result = await requestJson<KnowledgeBase>(KB_DETAIL_API_PATH, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            knowledge_base_id: knowledgeBaseId,
          }),
        })
        setSelectedKnowledgeBase(result)
        setSelectedKnowledgeBaseId(result.knowledge_base_id)
      } catch (error) {
        setManagementError(error instanceof Error ? error.message : '加载知识库详情失败。')
      }
    },
    [currentUserId, requestJson]
  )

  const loadDocuments = useCallback(
    async (
      knowledgeBaseId: string,
      page = documentPage,
      search = documentSearch
    ) => {
      if (!knowledgeBaseId) {
        setDocuments([])
        setDocumentTotal(0)
        return
      }

      setLoadingDocuments(true)
      setManagementError('')
      try {
        const result = await requestJson<PaginatedKnowledgeDocumentResponse>(
          KB_DOCUMENT_LIST_API_PATH,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: currentUserId,
              knowledge_base_id: knowledgeBaseId,
              search,
              page,
              page_size: DOCUMENT_PAGE_SIZE,
            }),
          }
        )
        setDocuments(result.items)
        setDocumentTotal(result.total)
      } catch (error) {
        setManagementError(error instanceof Error ? error.message : '加载文档失败。')
        setDocuments([])
        setDocumentTotal(0)
      } finally {
        setLoadingDocuments(false)
      }
    },
    [currentUserId, documentPage, documentSearch, requestJson]
  )

  const loadDocumentDetail = useCallback(
    async (knowledgeBaseId: string, documentId: string, page = documentChunkPage) => {
      if (!knowledgeBaseId || !documentId) {
        setSelectedDocumentDetail(null)
        return
      }

      setManagementError('')
      try {
        const result = await requestJson<KnowledgeDocumentDetailResponse>(
          KB_DOCUMENT_DETAIL_API_PATH,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: currentUserId,
              knowledge_base_id: knowledgeBaseId,
              document_id: documentId,
              page,
              page_size: DOCUMENT_CHUNK_PAGE_SIZE,
            }),
          }
        )
        setSelectedDocumentDetail(result)
      } catch (error) {
        setManagementError(error instanceof Error ? error.message : '加载文档详情失败。')
        setSelectedDocumentDetail(null)
      }
    },
    [currentUserId, documentChunkPage, requestJson]
  )

  const loadSkills = useCallback(async () => {
    setLoadingSkills(true)
    setSkillError('')
    try {
      const result = await requestJson<SkillListResponse>(SKILL_LIST_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search: '' }),
      })
      setSkills(result.items)
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '加载技能列表失败。')
      setSkills([])
    } finally {
      setLoadingSkills(false)
    }
  }, [requestJson])

  const loadAdminUsers = useCallback(
    async (search = '') => {
      if (actor.isGuest || actor.role !== 'admin') {
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
    [actor.isGuest, actor.role, requestJson]
  )

  useEffect(() => {
    void loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
  }, [currentUserId, knowledgeBasePage, knowledgeBaseSearch, loadKnowledgeBases])

  useEffect(() => {
    void loadSkills()
  }, [loadSkills])

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      setSelectedKnowledgeBase(null)
      setDocuments([])
      setDocumentTotal(0)
      return
    }
    void loadKnowledgeBaseDetail(selectedKnowledgeBaseId)
  }, [loadKnowledgeBaseDetail, selectedKnowledgeBaseId])

  useEffect(() => {
    if (!selectedKnowledgeBaseId) return
    void loadDocuments(selectedKnowledgeBaseId, documentPage, documentSearch)
  }, [documentPage, documentSearch, loadDocuments, selectedKnowledgeBaseId])

  useEffect(() => {
    if (!selectedKnowledgeBaseId || !selectedDocumentId || knowledgePage !== 'document-detail') {
      return
    }
    void loadDocumentDetail(selectedKnowledgeBaseId, selectedDocumentId, documentChunkPage)
  }, [
    documentChunkPage,
    knowledgePage,
    loadDocumentDetail,
    selectedDocumentId,
    selectedKnowledgeBaseId,
  ])

  const selectKnowledgeBase = useCallback(
    (knowledgeBase: KnowledgeBase) => {
      if (useKnowledgeBase && knowledgeBase.knowledge_base_id !== selectedKnowledgeBaseId) {
        clearChat()
        setCheckedDocumentIds([])
      }
      setSelectedKnowledgeBaseId(knowledgeBase.knowledge_base_id)
      setSelectedKnowledgeBase(knowledgeBase)
      setDocumentPage(1)
      setDocumentSearch('')
      setDocumentSearchInput('')
      setSelectedDocumentId('')
      setSelectedDocumentDetail(null)
      setDocumentChunkPage(1)
    },
    [clearChat, selectedKnowledgeBaseId, useKnowledgeBase]
  )

  const handleKnowledgeBaseToggle = (checked: boolean) => {
    if (checked !== useKnowledgeBase) {
      clearChat()
      setShowInterrupt(false)
      setInterruptData(null)
      requestModeRef.current = checked ? 'rag' : 'agent'
      requestKnowledgeBaseRef.current = checked ? selectedKnowledgeBase : null
    }
    setUseKnowledgeBase(checked)
  }

  const saveMcpConfig = () => {
    const trimmed = mcpConfigDraft.trim()

    if (!trimmed) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('rag_mcp_config')
        localStorage.setItem('rag_mcp_enabled', 'false')
      }
      setSavedMcpConfigText('')
      setMcpConfigDraft('')
      setMcpConfig(null)
      setMcpEnabled(false)
      setMcpNotice('MCP 配置已清空。')
      setMcpError('')
      return
    }

    const parsed = parseMcpConfig(trimmed)
    if (!parsed.config || parsed.error) {
      setMcpNotice('')
      setMcpError(parsed.error || 'MCP 配置无效，无法保存。')
      return
    }

    const formatted = JSON.stringify(parsed.config, null, 2)
    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_mcp_config', formatted)
    }

    setSavedMcpConfigText(formatted)
    setMcpConfigDraft(formatted)
    setMcpConfig(parsed.config)
    setMcpNotice(`已保存 ${parsed.serverSummaries.length} 个 MCP 服务配置。`)
    setMcpError('')
  }

  const formatMcpConfig = () => {
    const trimmed = mcpConfigDraft.trim()
    if (!trimmed) {
      setMcpNotice('')
      setMcpError('当前 MCP 草稿为空，没有可格式化的内容。')
      return
    }
    const parsed = parseMcpConfig(trimmed)
    if (!parsed.config || parsed.error) {
      setMcpNotice('')
      setMcpError(parsed.error || 'MCP 配置无效，无法格式化。')
      return
    }
    setMcpConfigDraft(JSON.stringify(parsed.config, null, 2))
    setMcpNotice('MCP 草稿已格式化，尚未保存到本地配置。')
    setMcpError('')
  }

  const toggleMcpEnabled = () => {
    if (mcpEnabled) {
      if (typeof window !== 'undefined') {
        localStorage.setItem('rag_mcp_enabled', 'false')
      }
      setMcpEnabled(false)
      setMcpNotice('MCP 已停用。')
      setMcpError('')
      return
    }

    if (mcpConfigDirty) {
      setMcpNotice('')
      setMcpError('当前 MCP 草稿尚未保存，请先保存后再启用。')
      return
    }

    if (!mcpConfig) {
      setMcpNotice('')
      setMcpError('请先保存一份有效的 MCP 配置后再启用。')
      return
    }

    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_mcp_enabled', 'true')
    }
    setMcpEnabled(true)
    setMcpNotice('MCP 已启用，后续通用 Agent 请求会附带该配置。')
    setMcpError('')
  }

  const loadMcpExample = () => {
    setMcpConfigDraft(DEFAULT_MCP_CONFIG_TEMPLATE)
    setMcpNotice('已填入 MCP 示例配置，请按你的服务地址修改后保存。')
    setMcpError('')
  }

  const clearMcpConfig = () => {
    setMcpConfigDraft('')
    setMcpNotice('已清空 MCP 草稿，点击“保存配置”后会同步清空本地配置。')
    setMcpError('')
  }

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
    email: string
    password: string
    role: 'admin' | 'user'
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
      setUserAdminNotice(`已创建账号 ${input.email}。`)
    } catch (error) {
      setUserAdminError(error instanceof Error ? error.message : '创建用户失败。')
    }
  }

  const updateAdminUserRole = async (userId: string, role: 'admin' | 'user') => {
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

  const openSkillUploadDialog = () => {
    skillUploadInputRef.current?.click()
  }

  const handleUploadSkill = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setUploadingSkills(true)
    setSkillNotice('')
    setSkillError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const result = await requestJson<SkillUploadResponse>(SKILL_UPLOAD_API_PATH, {
        method: 'POST',
        body: formData,
      })
      await loadSkills()
      setSkillNotice(
        `技能 "${result.skill.skill_name}" 上传完成，共解压 ${result.extracted_files} 个文件。`
      )
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '上传技能失败。')
    } finally {
      setUploadingSkills(false)
      event.target.value = ''
    }
  }

  const deleteSkill = async (skillName: string) => {
    if (!window.confirm(`确认删除技能 "${skillName}" 吗？`)) return

    setSkillNotice('')
    setSkillError('')
    try {
      const result = await requestJson<SkillDeleteResponse>(SKILL_DELETE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: skillName }),
      })
      await loadSkills()
      setSkillNotice(`技能 "${result.skill_name}" 已删除。`)
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '删除技能失败。')
    }
  }

  const openKnowledgeBaseLibrary = (knowledgeBase: KnowledgeBase) => {
    selectKnowledgeBase(knowledgeBase)
    navigateTo('knowledge', 'library-detail')
  }

  const openDocumentDetail = (document: KnowledgeDocument) => {
    setSelectedDocumentId(document.document_id)
    setDocumentChunkPage(1)
    navigateTo('knowledge', 'document-detail')
  }

  const createKnowledgeBase = async () => {
    const name = knowledgeBaseName.trim()
    if (!name) {
      setManagementError('知识库名称不能为空。')
      return
    }

    setSavingKnowledgeBase(true)
    setManagementError('')
    setManagementNotice('')
    try {
      const created = await requestJson<KnowledgeBase>(KB_CREATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          name,
          description: knowledgeBaseDescription.trim(),
        }),
      })
      setKnowledgeBasePage(1)
      await loadKnowledgeBases(1, knowledgeBaseSearch)
      selectKnowledgeBase(created)
      navigateTo('knowledge', 'library-detail')
      setKnowledgeBaseName('')
      setKnowledgeBaseDescription('')
      setShowCreateKnowledgeBaseModal(false)
      setManagementNotice(`知识库 "${created.name}" 已创建。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '创建知识库失败。')
    } finally {
      setSavingKnowledgeBase(false)
    }
  }

  /**
   * 更新指定知识库并刷新列表。
   *
   * Args:
   *   knowledgeBaseId: 知识库 ID。
   *   name: 知识库名称。
   *   description: 知识库描述。
   */
  const updateKnowledgeBase = async (
    knowledgeBaseId: string,
    name: string,
    description: string
  ) => {
    setSavingKnowledgeBase(true)
    setManagementError('')
    setManagementNotice('')
    try {
      const updated = await requestJson<KnowledgeBase>(KB_UPDATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          knowledge_base_id: knowledgeBaseId,
          name: name.trim(),
          description: description.trim(),
        }),
      })
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      selectKnowledgeBase(updated)
      setManagementNotice(`知识库 "${updated.name}" 已更新。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '更新知识库失败。')
      throw error
    } finally {
      setSavingKnowledgeBase(false)
    }
  }

  const deleteKnowledgeBase = async (knowledgeBaseId?: string) => {
    const targetId = knowledgeBaseId || selectedKnowledgeBase?.knowledge_base_id
    const targetName =
      knowledgeBases.find((item) => item.knowledge_base_id === targetId)?.name ||
      selectedKnowledgeBase?.name ||
      '知识库'

    if (!targetId) return
    if (!window.confirm(`确认删除知识库 "${targetName}" 及其索引数据吗？`)) return

    setSavingKnowledgeBase(true)
    setManagementError('')
    setManagementNotice('')
    try {
      await requestJson(KB_DELETE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          knowledge_base_id: targetId,
        }),
      })

      if (targetId === selectedKnowledgeBaseId) {
        setSelectedKnowledgeBaseId('')
        setSelectedKnowledgeBase(null)
        setSelectedDocumentId('')
        setSelectedDocumentDetail(null)
        setDocuments([])
        setDocumentTotal(0)
        navigateTo('knowledge', 'libraries')
      }
      setCheckedKnowledgeBaseIds((prev) => prev.filter((item) => item !== targetId))
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      setManagementNotice(`知识库 "${targetName}" 已删除。`)
      clearChat()
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '删除知识库失败。')
    } finally {
      setSavingKnowledgeBase(false)
    }
  }

  const bulkDeleteKnowledgeBases = async () => {
    if (checkedKnowledgeBaseIds.length === 0) return
    if (!window.confirm(`确认删除选中的 ${checkedKnowledgeBaseIds.length} 个知识库吗？`)) {
      return
    }

    setDeletingBulk(true)
    setManagementError('')
    setManagementNotice('')
    try {
      const result = await requestJson<BulkDeleteKnowledgeBaseResponse>(
        KB_BULK_DELETE_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            knowledge_base_ids: checkedKnowledgeBaseIds,
          }),
        }
      )
      if (result.deleted_ids.includes(selectedKnowledgeBaseId)) {
        setSelectedKnowledgeBaseId('')
        setSelectedKnowledgeBase(null)
        setSelectedDocumentId('')
        setSelectedDocumentDetail(null)
        setDocuments([])
        setDocumentTotal(0)
        clearChat()
        navigateTo('knowledge', 'libraries')
      }
      setCheckedKnowledgeBaseIds([])
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      setManagementNotice(`已删除 ${result.deleted_ids.length} 个知识库。`)
      if (Object.keys(result.failed).length > 0) {
        setManagementError(
          Object.entries(result.failed)
            .map(([id, message]) => `${id}: ${message}`)
            .join('\n')
        )
      }
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '批量删除知识库失败。')
    } finally {
      setDeletingBulk(false)
    }
  }

  const openUploadDialog = () => {
    uploadInputRef.current?.click()
  }

  const handleUploadFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!selectedKnowledgeBase || files.length === 0) return

    setUploadingDocuments(true)
    setManagementError('')
    setManagementNotice('')

    const formData = new FormData()
    formData.append('user_id', currentUserId)
    formData.append('knowledge_base_id', selectedKnowledgeBase.knowledge_base_id)
    files.forEach((file) => formData.append('files', file))

    try {
      const result = await requestJson<UploadResult>(KB_DOCUMENT_UPLOAD_API_PATH, {
        method: 'POST',
        body: formData,
      })
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      await loadKnowledgeBaseDetail(selectedKnowledgeBase.knowledge_base_id)
      await loadDocuments(selectedKnowledgeBase.knowledge_base_id, 1, documentSearch)
      setDocumentPage(1)

      const successCount = result.documents.length
      const errorCount = result.errors.length
      setManagementNotice(
        errorCount
          ? `成功入库 ${successCount} 个文件，失败 ${errorCount} 个。`
          : `已成功入库 ${successCount} 个文件。`
      )
      if (errorCount) {
        setManagementError(
          result.errors.map((item) => `${item.file_name}: ${item.error}`).join('\n')
        )
      }
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '上传文件失败。')
    } finally {
      setUploadingDocuments(false)
      event.target.value = ''
    }
  }

  const renameDocument = async (document: KnowledgeDocument) => {
    if (!selectedKnowledgeBase) return
    const nextName = window.prompt('请输入新的文档展示名称', document.display_name)
    if (!nextName) return

    setManagementError('')
    setManagementNotice('')
    try {
      await requestJson<KnowledgeDocument>(KB_DOCUMENT_UPDATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
          document_id: document.document_id,
          display_name: nextName,
        }),
      })
      await loadDocuments(selectedKnowledgeBase.knowledge_base_id, documentPage, documentSearch)
      if (selectedDocumentId === document.document_id) {
        await loadDocumentDetail(
          selectedKnowledgeBase.knowledge_base_id,
          document.document_id,
          documentChunkPage
        )
      }
      setManagementNotice(`文档 "${nextName}" 已更新。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '重命名文档失败。')
    }
  }

  const deleteDocument = async (documentId?: string, documentName?: string) => {
    if (!selectedKnowledgeBase || !documentId) return
    const targetName =
      documentName ||
      documents.find((item) => item.document_id === documentId)?.display_name ||
      '文档'
    if (!window.confirm(`确认删除文档 "${targetName}" 吗？`)) return

    setManagementError('')
    setManagementNotice('')
    try {
      await requestJson(KB_DOCUMENT_DELETE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
          document_id: documentId,
        }),
      })
      setCheckedDocumentIds((prev) => prev.filter((item) => item !== documentId))
      if (selectedDocumentId === documentId) {
        setSelectedDocumentId('')
        setSelectedDocumentDetail(null)
        navigateTo('knowledge', 'library-detail')
      }
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      await loadKnowledgeBaseDetail(selectedKnowledgeBase.knowledge_base_id)
      await loadDocuments(selectedKnowledgeBase.knowledge_base_id, documentPage, documentSearch)
      setManagementNotice(`文档 "${targetName}" 已删除。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '删除文档失败。')
    }
  }

  const bulkDeleteDocuments = async () => {
    if (!selectedKnowledgeBase || checkedDocumentIds.length === 0) return
    if (!window.confirm(`确认删除选中的 ${checkedDocumentIds.length} 个文档吗？`)) {
      return
    }

    setDeletingBulk(true)
    setManagementError('')
    setManagementNotice('')
    try {
      const result = await requestJson<BulkDeleteDocumentResponse>(
        KB_DOCUMENT_BULK_DELETE_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
            document_ids: checkedDocumentIds,
          }),
        }
      )
      setCheckedDocumentIds([])
      if (checkedDocumentIds.includes(selectedDocumentId)) {
        setSelectedDocumentId('')
        setSelectedDocumentDetail(null)
        navigateTo('knowledge', 'library-detail')
      }
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      await loadKnowledgeBaseDetail(selectedKnowledgeBase.knowledge_base_id)
      await loadDocuments(selectedKnowledgeBase.knowledge_base_id, documentPage, documentSearch)
      setManagementNotice(`已删除 ${result.deleted_ids.length} 个文档。`)
      if (Object.keys(result.failed).length > 0) {
        setManagementError(
          Object.entries(result.failed)
            .map(([id, message]) => `${id}: ${message}`)
            .join('\n')
        )
      }
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '批量删除文档失败。')
    } finally {
      setDeletingBulk(false)
    }
  }

  /**
   * 将当前思考块的耗时写入对应的消息块。
   *
   * Args:
   * - 无。
   */
  const finishReasoningBlock = useCallback(() => {
    if (reasoningStartTimeRef.current === null) return

    const duration = Date.now() - reasoningStartTimeRef.current
    updateAssistantMessage((message) => {
      const reasoningBlocks = message.reasoningBlocks
      if (!reasoningBlocks?.length) return message

      return {
        ...message,
        reasoningBlocks: reasoningBlocks.map((block, index) =>
          index === reasoningBlocks.length - 1 ? { ...block, duration } : block
        ),
      }
    })
    reasoningStartTimeRef.current = null
  }, [updateAssistantMessage])

  const finishAssistantDuration = useCallback(() => {
    const finishedAt = Date.now()
    updateAssistantMessage((message) => {
      if (message.duration !== undefined || message.startedAt === undefined) {
        return message
      }
      return {
        ...message,
        duration: Math.max(0, finishedAt - message.startedAt),
      }
    })
  }, [updateAssistantMessage])

  const applyAgUiInterrupt = useCallback(
    (interrupt: AgUiInterrupt) => {
      if (lastAssistantStreamEventRef.current === 'reasoning') {
        finishReasoningBlock()
      }
      const nextInterruptData: InterruptData = {
        interrupt_id: interrupt.interrupt_id,
        action_requests: interrupt.action_requests ?? [],
        review_configs: interrupt.review_configs,
      }
      const interruptedToolNames = new Set(
        nextInterruptData.action_requests
          .map((action) => action.name)
          .filter(
            (name): name is string =>
              Boolean(name) && name !== 'ask_user'
          )
      )
      if (interruptedToolNames.size > 0) {
        updateAssistantMessage((message) => {
          const removedToolCallIds = new Set(
            (message.toolData || [])
              .filter((tool) => interruptedToolNames.has(tool.toolCall.name))
              .map((tool) => tool.toolCall.id)
          )
          if (removedToolCallIds.size === 0) return message
          return {
            ...message,
            toolData: (message.toolData || []).filter(
              (tool) => !removedToolCallIds.has(tool.toolCall.id)
            ),
            messageItems: (message.messageItems || []).filter(
              (item) =>
                item.type !== 'tool' ||
                !removedToolCallIds.has(item.toolCallId)
            ),
          }
        })
      }
      setInterruptData(nextInterruptData)
      setShowInterrupt(true)
      const activeThreadId = activeThreadIdRef.current
      if (activeThreadId) {
        const runtime = getThreadRuntime(activeThreadId)
        runtime.showInterrupt = true
        runtime.interruptData = nextInterruptData
      }
      setIsProcessing(false)
      setStatus('ready')
      lastAssistantStreamEventRef.current = 'interrupt'
    },
    [
      finishReasoningBlock,
      getThreadRuntime,
      updateAssistantMessage,
    ]
  )

  const handleAgUiEvent = useCallback(
    (event: AgUiEvent): 'interrupt' | 'finished' | null => {
      const eventType = event.type

      if (eventType === 'TEXT_MESSAGE_CONTENT' || eventType === 'TEXT_MESSAGE_CHUNK') {
        const delta =
          typeof event.delta === 'string'
            ? event.delta
            : typeof event.content === 'string'
              ? event.content
              : ''
        if (!delta) return null
        if (lastAssistantStreamEventRef.current === 'reasoning') {
          finishReasoningBlock()
        }
        const shouldAppendToLastBlock =
          lastAssistantStreamEventRef.current === 'content'
        updateAssistantMessage((message) => {
          const { contentBlocks, messageItems } = appendContentToken(
            message.contentBlocks,
            message.messageItems,
            delta,
            shouldAppendToLastBlock,
            () => {
              contentBlockCounterRef.current += 1
              return `${message.id}_content_${contentBlockCounterRef.current}`
            }
          )
          return {
            ...message,
            content: `${message.content}${delta}`,
            contentBlocks,
            messageItems,
          }
        })
        lastAssistantStreamEventRef.current = 'content'
        return null
      }

      if (
        eventType === 'THINKING_TEXT_MESSAGE_CONTENT' ||
        eventType === 'REASONING_MESSAGE_CONTENT' ||
        eventType === 'REASONING_MESSAGE_CHUNK'
      ) {
        const delta = typeof event.delta === 'string' ? event.delta : ''
        if (!delta) return null
        const shouldStartNewBlock =
          lastAssistantStreamEventRef.current !== 'reasoning'
        if (shouldStartNewBlock) {
          reasoningStartTimeRef.current = Date.now()
        }
        updateAssistantMessage((message) => {
          const { reasoningBlocks, messageItems } = appendReasoningToken(
            message.reasoningBlocks,
            message.messageItems,
            delta,
            shouldStartNewBlock,
            () => {
              reasoningBlockCounterRef.current += 1
              return `${message.id}_reasoning_${reasoningBlockCounterRef.current}`
            },
            message.reasoningContent
          )
          return {
            ...message,
            reasoningBlocks,
            messageItems,
            reasoningContent: `${message.reasoningContent || ''}${delta}`,
          }
        })
        lastAssistantStreamEventRef.current = 'reasoning'
        return null
      }

      if (eventType === 'MESSAGES_SNAPSHOT') {
        const snapshotText = getAgUiAssistantSnapshotText(event)
        if (!snapshotText) return null
        updateAssistantMessage((message) => {
          if (message.content === snapshotText) return message
          if (message.content && !snapshotText.startsWith(message.content)) {
            return message
          }
          const missing = snapshotText.slice(message.content.length)
          if (!missing) return message
          const { contentBlocks, messageItems } = appendContentToken(
            message.contentBlocks,
            message.messageItems,
            missing,
            message.content.length > 0,
            () => {
              contentBlockCounterRef.current += 1
              return `${message.id}_content_${contentBlockCounterRef.current}`
            }
          )
          return {
            ...message,
            content: snapshotText,
            contentBlocks,
            messageItems,
          }
        })
        lastAssistantStreamEventRef.current = 'content'
        return null
      }

      if (eventType === 'TOOL_CALL_START') {
        const toolCallId = String(event.toolCallId || '')
        const toolName = String(event.toolCallName || 'tool')
        if (!toolCallId) return null
        if (lastAssistantStreamEventRef.current === 'reasoning') {
          finishReasoningBlock()
        }
        toolCallStartTimesRef.current[toolCallId] = Date.now()
        updateAssistantMessage((message) => {
          const tools = [...(message.toolData || [])]
          if (!tools.some((tool) => tool.toolCall.id === toolCallId)) {
            tools.push({
              toolCall: { id: toolCallId, name: toolName, args: {} },
              toolOutput: [],
            })
          }
          return {
            ...message,
            toolData: tools,
            messageItems: ensureToolItem(message.messageItems || [], toolCallId),
          }
        })
        lastAssistantStreamEventRef.current = 'tool'
        return null
      }

      if (eventType === 'TOOL_CALL_ARGS') {
        const toolCallId = String(event.toolCallId || '')
        const delta = typeof event.delta === 'string' ? event.delta : ''
        if (!toolCallId || !delta) return null
        const raw = `${toolCallArgsRef.current[toolCallId] || ''}${delta}`
        toolCallArgsRef.current[toolCallId] = raw
        let parsed: Record<string, unknown> = {}
        try {
          const value = JSON.parse(raw) as unknown
          if (value && typeof value === 'object' && !Array.isArray(value)) {
            parsed = value as Record<string, unknown>
          }
        } catch {
          // 工具参数仍是流式 JSON 片段，等待后续 delta 补齐。
        }
        if (Object.keys(parsed).length > 0) {
          updateAssistantMessage((message) => ({
            ...message,
            toolData: (message.toolData || []).map((tool) =>
              tool.toolCall.id === toolCallId
                ? { ...tool, toolCall: { ...tool.toolCall, args: parsed } }
                : tool
            ),
          }))
        }
        return null
      }

      if (eventType === 'TOOL_CALL_RESULT') {
        const toolCallId = String(event.toolCallId || '')
        if (!toolCallId) return null
        const now = Date.now()
        const startTime = toolCallStartTimesRef.current[toolCallId]
        const toolDuration = startTime ? now - startTime : undefined
        if (toolDuration !== undefined) {
          setToolCallDurations((prev) => ({
            ...prev,
            [toolCallId]: toolDuration,
          }))
          delete toolCallStartTimesRef.current[toolCallId]
        }
        if (processedToolCallIdsRef.current.has(toolCallId)) return null
        processedToolCallIdsRef.current.add(toolCallId)
        const normalizedOutput = {
          tool_call_id: toolCallId,
          content: stringifyToolContent(event.content),
        }
        updateAssistantMessage((message) => {
          const tools = [...(message.toolData || [])]
          const existingToolIndex = tools.findIndex(
            (tool) => tool.toolCall.id === toolCallId
          )
          if (existingToolIndex >= 0) {
            const existingTool = tools[existingToolIndex]
            if (
              existingTool.toolOutput?.some(
                (output) => output.content === normalizedOutput.content
              )
            ) {
              return message
            }
            tools[existingToolIndex] = {
              ...existingTool,
              duration: toolDuration ?? existingTool.duration,
              toolOutput: [
                ...(existingTool.toolOutput || []),
                normalizedOutput,
              ],
            }
          } else {
            tools.push({
              toolCall: { id: toolCallId, name: 'tool', args: {} },
              duration: toolDuration,
              toolOutput: [normalizedOutput],
            })
          }
          return {
            ...message,
            toolData: tools,
            messageItems: ensureToolItem(message.messageItems || [], toolCallId),
          }
        })
        lastAssistantStreamEventRef.current = 'tool'
        return null
      }

      if (eventType === 'CUSTOM') {
        const interrupt = getAgUiInterrupt(event)
        if (interrupt) {
          applyAgUiInterrupt(interrupt)
          return 'interrupt'
        }

        const recommendedQuestions = getRecommendedQuestions(event)
        const assistantMessageId = currentAssistantMessageIdRef.current
        if (recommendedQuestions.length > 0 && assistantMessageId) {
          setMessagesAndRef((prev) =>
            prev.map((message) =>
              message.role === 'ai'
                ? {
                    ...message,
                    recommendedQuestions:
                      message.id === assistantMessageId
                        ? recommendedQuestions
                        : undefined,
                  }
                : message
            )
          )
        }
        return null
      }

      if (eventType === 'RUN_ERROR') {
        finishAssistantDuration()
        throw new ChatRequestError(
          createChatError(
            'run',
            String(event.message || 'Agent run failed')
          )
        )
      }

      if (eventType === 'RUN_FINISHED') {
        const interrupt = getAgUiInterruptOutcome(event)
        if (interrupt) {
          applyAgUiInterrupt(interrupt)
          return 'interrupt'
        }
        finishAssistantDuration()
        return 'finished'
      }

      return null
    },
    [
      applyAgUiInterrupt,
      finishReasoningBlock,
      finishAssistantDuration,
      setMessagesAndRef,
      updateAssistantMessage,
    ]
  )

  const isCurrentStream = useCallback(
    (threadId: string, generation: number) =>
      activeThreadIdRef.current === threadId &&
      streamGenerationRef.current === generation,
    []
  )

  const readEventStream = useCallback(
    async (response: Response, threadId: string, generation: number) => {
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let interrupted = false
      let completed = false
      let stale = false

      const processChunk = (chunk: string) => {
        if (!isCurrentStream(threadId, generation)) {
          stale = true
          return
        }

        const normalized = chunk.replace(/\r\n/g, '\n')
        const parts = normalized.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!isCurrentStream(threadId, generation)) {
            stale = true
            return
          }
          const frame = parseAgUiSseFrame(part)
          if (!frame) continue
          const runtime = getThreadRuntime(threadId)
          if (frame.id) {
            lastEventIdRef.current = frame.id
            runtime.lastEventId = frame.id
          }
          const handledEvent = handleAgUiEvent(frame.event)
          if (handledEvent === 'interrupt') {
            interrupted = true
            runtime.processing = false
            runtime.status = 'ready'
            runtime.messages = messagesRef.current
            setThreadRunning(threadId, false)
          }
          if (handledEvent === 'finished') {
            completed = true
            runtime.processing = false
            runtime.status = 'ready'
            runtime.messages = messagesRef.current
            setThreadRunning(threadId, false)
            setIsProcessing(false)
            setStatus('ready')
          }
        }
      }

      while (true) {
        if (!isCurrentStream(threadId, generation)) {
          stale = true
          break
        }
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        processChunk(buffer)
        if (completed || stale) {
          await reader.cancel()
          break
        }
      }

      if (!stale) {
        buffer += decoder.decode()
        if (buffer.trim()) {
          processChunk(`${buffer}\n\n`)
        }
      }

      return { interrupted, completed, stale }
    },
    [getThreadRuntime, handleAgUiEvent, isCurrentStream, setThreadRunning]
  )

  const subscribeAgUiEvents = useCallback(
    async (
      basePath: string,
      runId: string,
      threadId: string,
      generation: number,
      signal?: AbortSignal
    ) => {
      if (!runId) throw new Error('Run ID missing')
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (!isCurrentStream(threadId, generation)) {
          return { interrupted: false, completed: false, stale: true }
        }
        const response = await fetch(
          getApiUrl(`${basePath}/${encodeURIComponent(runId)}/events`),
          {
            headers: withAuthHeaders({
              Accept: 'text/event-stream',
              ...(lastEventIdRef.current
                ? { 'Last-Event-ID': lastEventIdRef.current }
                : {}),
            }),
            signal,
          }
        )
        if (!response.ok) {
          throw new ChatRequestError(
            await createHttpChatError(response, 'stream')
          )
        }
        const result = await readEventStream(response, threadId, generation)
        if (result.stale || result.completed || result.interrupted) return result
        await new Promise((resolve) => setTimeout(resolve, 300 * (attempt + 1)))
      }
      throw new ChatRequestError(
        createChatError('stream', 'AG-UI 事件流中断，重放次数已用尽')
      )
    },
    [isCurrentStream, readEventStream, withAuthHeaders]
  )

  const startAgUiRun = useCallback(
    async (
      basePath: string,
      runInput: Record<string, unknown>,
      threadId: string,
      generation: number,
      signal?: AbortSignal
    ) => {
      const createResponse = await fetch(getApiUrl(basePath), {
        method: 'POST',
        headers: withAuthHeaders({
          'Content-Type': 'application/json',
          Accept: 'application/json',
        }),
        body: JSON.stringify(runInput),
        signal,
      })
      if (!createResponse.ok) {
        throw new ChatRequestError(
          await createHttpChatError(createResponse, 'http')
        )
      }
      const snapshot = (await createResponse.json()) as { runId?: string }
      const runId = snapshot.runId
      if (!runId) throw new Error('Run ID missing')

      const runtime = getThreadRuntime(threadId)
      runtime.runId = runId
      runtime.basePath = basePath
      runtime.runInput = runInput
      runtime.lastEventId = null
      runtime.processing = true
      runtime.status = 'connecting'
      setThreadRunning(threadId, true)

      if (!isCurrentStream(threadId, generation)) {
        return { interrupted: false, completed: false, stale: true }
      }

      currentRunIdRef.current = runId
      lastEventIdRef.current = null
      return subscribeAgUiEvents(basePath, runId, threadId, generation, signal)
    },
    [
      getThreadRuntime,
      isCurrentStream,
      setThreadRunning,
      subscribeAgUiEvents,
      withAuthHeaders,
    ]
  )

  const resumeAgUiRun = useCallback(
    async (
      basePath: string,
      runInput: Record<string, unknown>,
      threadId: string,
      generation: number,
      signal?: AbortSignal
    ) => {
      const runId = currentRunIdRef.current
      if (!runId) throw new Error('当前没有可恢复的 Run')
      const resumeResponse = await fetch(
        getApiUrl(`${basePath}/${encodeURIComponent(runId)}/resume`),
        {
          method: 'POST',
          headers: withAuthHeaders({
            'Content-Type': 'application/json',
            Accept: 'application/json',
          }),
          body: JSON.stringify(runInput),
          signal,
        }
      )
      if (!resumeResponse.ok) {
        throw new ChatRequestError(
          await createHttpChatError(resumeResponse, 'resume')
        )
      }
      setThreadRunning(threadId, true)
      return subscribeAgUiEvents(basePath, runId, threadId, generation, signal)
    },
    [setThreadRunning, subscribeAgUiEvents, withAuthHeaders]
  )

  const resumeThreadStream = useCallback(
    async (runtime: ThreadRuntime) => {
      if (!runtime.runId || !runtime.processing) return

      const controller = new AbortController()
      runtime.abortController = controller
      abortControllerRef.current = controller
      const generation = streamGenerationRef.current

      const refreshTerminalState = async (): Promise<boolean> => {
        if (!runtime.runId) return false
        try {
          const snapshot = await requestJson<{ status?: string }>(
            `${runtime.basePath}/${encodeURIComponent(runtime.runId)}`
          )
          if (!snapshot.status || isActiveRunStatus(snapshot.status)) {
            return false
          }
          runtime.processing = false
          runtime.status = snapshot.status === 'error' ? 'error' : 'ready'
          if (activeThreadIdRef.current === runtime.threadId) {
            setIsProcessing(false)
            setStatus(runtime.status)
          }
          setThreadRunning(runtime.threadId, false)
          return true
        } catch {
          return false
        }
      }

      try {
        const result = await subscribeAgUiEvents(
          runtime.basePath,
          runtime.runId,
          runtime.threadId,
          generation,
          controller.signal
        )
        if (result.stale) return
        if (!result.completed && !result.interrupted) {
          if (await refreshTerminalState()) return
          runtime.processing = false
          runtime.status = 'error'
          if (activeThreadIdRef.current === runtime.threadId) {
            setIsProcessing(false)
            setStatus('error')
          }
          setThreadRunning(runtime.threadId, false)
        }
      } catch (error) {
        if (!isAbortError(error)) {
          if (await refreshTerminalState()) return
          runtime.processing = false
          runtime.status = 'error'
          if (activeThreadIdRef.current === runtime.threadId) {
            setIsProcessing(false)
            setStatus('error')
          }
          setThreadRunning(runtime.threadId, false)
        }
      } finally {
        if (runtime.abortController === controller) {
          runtime.abortController = null
        }
      }
    },
    [requestJson, setThreadRunning, subscribeAgUiEvents]
  )

  const switchToThread = useCallback(
    async (targetThreadId: string) => {
      if (targetThreadId === activeThreadIdRef.current) return

      const previousRuntime = persistActiveRuntime()
      streamGenerationRef.current += 1
      previousRuntime?.abortController?.abort()
      if (previousRuntime) {
        previousRuntime.abortController = null
      }
      abortControllerRef.current = null

      const existingRuntime = threadRuntimesRef.current.get(targetThreadId)
      if (existingRuntime) {
        if (existingRuntime.processing && !existingRuntime.runId) {
          existingRuntime.processing = false
          existingRuntime.status = 'ready'
        }
        syncRuntimeToView(existingRuntime)
        setThreadRunning(targetThreadId, existingRuntime.processing)
        if (existingRuntime.processing && existingRuntime.runId) {
          void resumeThreadStream(existingRuntime)
        }
        return
      }

      const runtime = createThreadRuntime(targetThreadId)
      runtime.basePath = aguiApiPath
      threadRuntimesRef.current.set(targetThreadId, runtime)
      syncRuntimeToView(runtime)
      setThreadRunning(targetThreadId, false)

      let stateMessages: unknown = []
      let messageCreatedAt: unknown = undefined
      try {
        const response = await requestJson<{
          messages?: unknown
          message_created_at?: unknown
        }>(AGUI_THREAD_STATE_API_PATH(targetThreadId))
        stateMessages = response.messages
        messageCreatedAt = response.message_created_at
      } catch (error) {
        if (!(error instanceof Error) || !error.message.includes('404')) {
          throw error
        }
      }
      const runsResponse = await requestJson<ThreadRunListResponse>(
        AGUI_THREAD_RUNS_API_PATH(targetThreadId)
      )
      const latestRun = runsResponse.items[0]
      const historyCreatedAt =
        latestRun?.updatedAt != null ? latestRun.updatedAt * 1000 : undefined
      runtime.messages = toHistoryMessages(
        stateMessages,
        messageCreatedAt,
        historyCreatedAt
      )
      if (activeThreadIdRef.current === targetThreadId) {
        messagesRef.current = runtime.messages
        setMessagesAndRef(runtime.messages)
      }
      if (latestRun) {
        runtime.agentId = latestRun.agentId
      }
      if (!latestRun || !isActiveRunStatus(latestRun.status)) return

      runtime.runId = latestRun.runId
      runtime.lastEventId = latestRun.lastEventId
      runtime.processing = true
      runtime.status = 'connecting'
      if (activeThreadIdRef.current !== targetThreadId) {
        setThreadRunning(targetThreadId, true)
        return
      }
      if (activeThreadIdRef.current === targetThreadId) {
        syncRuntimeToView(runtime)
      }
      setThreadRunning(targetThreadId, true)
      void resumeThreadStream(runtime)
    },
    [
      aguiApiPath,
      persistActiveRuntime,
      requestJson,
      resumeThreadStream,
      setMessagesAndRef,
      setThreadRunning,
      syncRuntimeToView,
    ]
  )

  useEffect(() => {
    switchToThreadRef.current = switchToThread
  }, [switchToThread])

  const sendMessage = async (recommendedQuestion?: string) => {
    const query = (recommendedQuestion ?? inputValue).trim()
    if (!query || isProcessing || !sessionId) return
    const threadId = sessionId
    const generation = streamGenerationRef.current + 1
    streamGenerationRef.current = generation
    const runtime = getThreadRuntime(threadId)

    const selectedAgentId = runtime.agentId ?? (useKnowledgeBase ? 'rag' : 'agent')
    const requestMode: RequestMode = selectedAgentId === 'rag' ? 'rag' : 'agent'
    if (
      availableAgents.length > 0 &&
      !availableAgents.some((agent) => agent.id === selectedAgentId)
    ) {
      setManagementError(`智能体 ${selectedAgentId} 当前不可用。`)
      return
    }
    const requestMcpConfig = requestMode === 'agent' && mcpEnabled ? mcpConfig : null
    if (requestMode === 'rag' && !selectedKnowledgeBase) {
      setManagementError('启用知识库问答后，必须先选择一个知识库。')
      navigateTo('knowledge', 'libraries')
      return
    }
    if (requestMode === 'agent' && mcpEnabled && !requestMcpConfig) {
      setMcpNotice('')
      setMcpError('MCP 已启用，但当前没有有效配置，请先在 MCP 管理中保存配置。')
      navigateTo('mcp')
      return
    }

    setMessagesAndRef((prev) =>
      prev.map((message) =>
        message.recommendedQuestions
          ? { ...message, recommendedQuestions: undefined }
          : message
      )
    )
    const userMessageId = generateMessageId()
    const userMessageCreatedAt = Date.now()
    addMessage({
      id: userMessageId,
      role: 'user',
      content: query,
      createdAt: userMessageCreatedAt,
    })
    setInputValue('')

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    setIsProcessing(true)
    setStatus('connecting')
    setToolCallDurations({})
    setThreadRunning(threadId, true)
    runtime.processing = true
    runtime.status = 'connecting'
    runtime.basePath = aguiApiPath
    runtime.agentId = selectedAgentId

    const assistantMessageId = generateMessageId()
    currentAssistantMessageIdRef.current = assistantMessageId
    processedToolCallIdsRef.current.clear()
    lastAssistantStreamEventRef.current = null
    reasoningStartTimeRef.current = null
    toolCallStartTimesRef.current = {}
    toolCallArgsRef.current = {}
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    requestModeRef.current = requestMode
    requestKnowledgeBaseRef.current = selectedKnowledgeBase
    requestMcpConfigRef.current = requestMcpConfig
    addMessage({
      id: assistantMessageId,
      role: 'ai',
      content: '',
      createdAt: Date.now(),
      toolData: [],
      startedAt: Date.now(),
    })
    runtime.messages = messagesRef.current
    runtime.assistantMessageId = assistantMessageId
    runtime.requestMode = requestMode
    runtime.requestKnowledgeBase = selectedKnowledgeBase
    runtime.requestMcpConfig = requestMcpConfig

    abortControllerRef.current = new AbortController()
    runtime.abortController = abortControllerRef.current

    try {
      const state: Record<string, unknown> = {
        internet_search: internetSearch,
        deep_thinking: deepThinking,
      }
      if (requestMode === 'rag' && selectedKnowledgeBase) {
        state.index_name = selectedKnowledgeBase.passage_index
        state.graph_name = selectedKnowledgeBase.index_prefix
      } else if (requestMode === 'agent' && requestMcpConfig) {
        state.mcp_config = requestMcpConfig
      }
      const runInput = createAgUiRunInput({
        agentId: selectedAgentId,
        threadId,
        runId: generateMessageId(),
        messageId: generateMessageId(),
        query,
        state,
      })
      currentRunInputRef.current = runInput as unknown as Record<string, unknown>
      runtime.runInput = currentRunInputRef.current
      await startAgUiRun(
        runtime.basePath,
        currentRunInputRef.current,
        threadId,
        generation,
        abortControllerRef.current.signal
      )
      if (isCurrentStream(threadId, generation)) {
        setStatus('ready')
      }
    } catch (error: unknown) {
      if (!isAbortError(error)) {
        runtime.processing = false
        runtime.status = 'error'
        setThreadRunning(threadId, false)
        if (isCurrentStream(threadId, generation)) {
          setStatus('error')
          applyAssistantError(assistantMessageId, error)
          registerRetryAction(assistantMessageId, async () => {
            setMessagesAndRef((prev) =>
              prev.filter(
                (message) =>
                  message.id !== userMessageId &&
                  message.id !== assistantMessageId
              )
            )
            await sendMessage(query)
          })
        }
      }
    } finally {
      if (isCurrentStream(threadId, generation)) {
        finishReasoningBlock()
        setIsProcessing(false)
        runtime.processing = false
        runtime.status = 'ready'
        runtime.messages = messagesRef.current
        runtime.lastEventId = lastEventIdRef.current
        runtime.abortController = null
        abortControllerRef.current = null
      }
      void loadHistorySessions()
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  /**
   * 发送用户点击的推荐问题。
   *
   * Args:
   * - question: 推荐问题文本。
   */
  const askRecommendedQuestion = (question: string) => {
    if (isProcessing) return

    setInputValue(question)
    void sendMessage(question)
  }

  const abortRequest = () => {
    const runId = currentRunIdRef.current
    const basePath = aguiApiPath
    const threadId = activeThreadIdRef.current
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    if (threadId) {
      const runtime = getThreadRuntime(threadId)
      runtime.processing = false
      runtime.status = 'ready'
      runtime.abortController = null
      setThreadRunning(threadId, false)
    }
    if (runId) {
      void fetch(getApiUrl(`${basePath}/${encodeURIComponent(runId)}/cancel`), {
        method: 'POST',
        headers: withAuthHeaders(),
      })
    }
  }

  const handleInterruptAction = async (
    decision: 'approve' | 'reject' | 'edit',
    editedActions?: Array<{ name: string; args: Record<string, unknown> }>,
    options?: { skipStatusMessage?: boolean }
  ) => {
    if (!interruptData || !('action_requests' in interruptData)) return

    const requestMode = requestModeRef.current
    const requestKnowledgeBase = requestKnowledgeBaseRef.current
    const requestMcpConfig = requestMcpConfigRef.current
    const threadId = activeThreadIdRef.current
    const generation = streamGenerationRef.current + 1
    streamGenerationRef.current = generation
    const runtime = getThreadRuntime(threadId)
    if (requestMode === 'rag' && !requestKnowledgeBase) {
      setManagementError('当前中断来自知识库问答，但未找到对应知识库，请重新发起请求。')
      setShowInterrupt(false)
      setInterruptData(null)
      return
    }

    setShowInterrupt(false)
    runtime.showInterrupt = false
    if (!options?.skipStatusMessage) {
      addMessage({
        id: generateMessageId(),
        role: 'user',
        content:
          decision === 'approve'
            ? '已批准继续执行。'
            : decision === 'reject'
              ? '已拒绝继续执行。'
              : '已修改参数并继续执行。',
      })
    }

    setIsProcessing(true)
    setStatus('connecting')
    setThreadRunning(threadId, true)
    runtime.processing = true
    runtime.status = 'connecting'
    lastAssistantStreamEventRef.current = null
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    abortControllerRef.current = new AbortController()
    runtime.abortController = abortControllerRef.current
    let receivedInterrupt = false

    try {
      const decisions: ResumeDecision[] = (interruptData.action_requests || []).map(
        (action, index) => {
          if (decision === 'edit' && editedActions?.[index]) {
            return {
              type: 'edit',
              edited_action: editedActions[index],
            }
          }
          if (decision === 'reject') {
            return {
              type: 'reject',
              message: `用户拒绝执行工具 ${action.name}。`,
            }
          }
          return { type: 'approve' }
        }
      )

      const baseInput = currentRunInputRef.current
      if (!baseInput) throw new Error('当前没有可恢复的 Run')
      const interruptId = interruptData.interrupt_id
      if (!interruptId) throw new Error('当前中断缺少 interruptId，无法恢复')
      const forwardedProps = {
        ...(baseInput.forwardedProps as Record<string, unknown> | undefined),
      }
      delete forwardedProps.command
      const runInput = {
        ...baseInput,
        forwardedProps,
        resume: [
          {
            interruptId,
            status: 'resolved',
            payload: { decisions },
          },
        ],
      }
      currentRunInputRef.current = runInput
      runtime.runInput = runInput
      const streamResult = await resumeAgUiRun(
        aguiApiPath,
        runInput,
        threadId,
        generation,
        abortControllerRef.current.signal
      )
      receivedInterrupt = streamResult.interrupted
      if (isCurrentStream(threadId, generation)) {
        setStatus('ready')
      }
    } catch (error: unknown) {
      if (!isAbortError(error)) {
        runtime.processing = false
        runtime.status = 'error'
        setThreadRunning(threadId, false)
        if (isCurrentStream(threadId, generation)) {
          setStatus('error')
          const assistantMessageId = currentAssistantMessageIdRef.current
          applyAssistantError(assistantMessageId, error)
          if (assistantMessageId) {
            registerRetryAction(assistantMessageId, () =>
              handleInterruptAction(decision, editedActions, {
                skipStatusMessage: true,
              })
            )
          }
        }
      }
    } finally {
      if (isCurrentStream(threadId, generation) && runtime.status !== 'error') {
        finishReasoningBlock()
        setIsProcessing(false)
        runtime.processing = false
        runtime.status = 'ready'
        runtime.messages = messagesRef.current
        runtime.lastEventId = lastEventIdRef.current
        runtime.abortController = null
        abortControllerRef.current = null
        if (!receivedInterrupt) {
          setInterruptData(null)
          runtime.interruptData = null
        }
      }
    }
  }

  const handleAskUserResponse = async (answer: string) => {
    if (
      !interruptData ||
      interruptData.action_requests.length !== 1 ||
      interruptData.action_requests[0].name !== 'ask_user'
    ) {
      return
    }

    const requestMode = requestModeRef.current
    const requestKnowledgeBase = requestKnowledgeBaseRef.current
    const requestMcpConfig = requestMcpConfigRef.current
    const threadId = activeThreadIdRef.current
    const generation = streamGenerationRef.current + 1
    streamGenerationRef.current = generation
    const runtime = getThreadRuntime(threadId)
    if (requestMode === 'rag' && !requestKnowledgeBase) {
      setManagementError('当前中断来自知识库问答，但未找到对应知识库，请重新发起请求。')
      setShowInterrupt(false)
      setInterruptData(null)
      return
    }

    setShowInterrupt(false)
    runtime.showInterrupt = false
    updateAssistantMessage((message) => {
      const toolIndex = [...(message.toolData || [])]
        .map((tool, index) => ({ tool, index }))
        .reverse()
        .find(({ tool }) => tool.toolCall.name === 'ask_user')?.index
      if (toolIndex === undefined) return message

      const tool = message.toolData?.[toolIndex]
      if (!tool) return message
      const responseContent = stringifyToolContent(answer)
      if (tool.toolOutput?.some((item) => item.content === responseContent)) {
        return message
      }

      const toolData = [...(message.toolData || [])]
      toolData[toolIndex] = {
        ...tool,
        toolOutput: [
          ...(tool.toolOutput || []),
          {
            tool_call_id: tool.toolCall.id,
            content: responseContent,
          },
        ],
      }
      return { ...message, toolData }
    })
    setIsProcessing(true)
    setStatus('connecting')
    setThreadRunning(threadId, true)
    runtime.processing = true
    runtime.status = 'connecting'
    lastAssistantStreamEventRef.current = null
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    abortControllerRef.current = new AbortController()
    runtime.abortController = abortControllerRef.current
    let receivedInterrupt = false

    try {
      const baseInput = currentRunInputRef.current
      if (!baseInput) throw new Error('当前没有可恢复的 Run')
      const interruptId = interruptData.interrupt_id
      if (!interruptId) throw new Error('当前中断缺少 interruptId，无法恢复')
      const forwardedProps = {
        ...(baseInput.forwardedProps as Record<string, unknown> | undefined),
      }
      delete forwardedProps.command
      const runInput = {
        ...baseInput,
        forwardedProps,
        resume: [
          {
            interruptId,
            status: 'resolved',
            payload: {
              decisions: [{ type: 'respond', message: answer }],
            },
          },
        ],
      }
      currentRunInputRef.current = runInput
      runtime.runInput = runInput
      const streamResult = await resumeAgUiRun(
        aguiApiPath,
        runInput,
        threadId,
        generation,
        abortControllerRef.current.signal
      )
      receivedInterrupt = streamResult.interrupted
      if (isCurrentStream(threadId, generation)) {
        setStatus('ready')
      }
    } catch (error: unknown) {
      if (!isAbortError(error)) {
        runtime.processing = false
        runtime.status = 'error'
        setThreadRunning(threadId, false)
        if (isCurrentStream(threadId, generation)) {
          setStatus('error')
          const assistantMessageId = currentAssistantMessageIdRef.current
          applyAssistantError(assistantMessageId, error)
          if (assistantMessageId) {
            registerRetryAction(assistantMessageId, () =>
              handleAskUserResponse(answer)
            )
          }
        }
      }
    } finally {
      if (isCurrentStream(threadId, generation) && runtime.status !== 'error') {
        finishReasoningBlock()
        setIsProcessing(false)
        runtime.processing = false
        runtime.status = 'ready'
        runtime.messages = messagesRef.current
        runtime.lastEventId = lastEventIdRef.current
        runtime.abortController = null
        abortControllerRef.current = null
        if (!receivedInterrupt) {
          setInterruptData(null)
          runtime.interruptData = null
        }
      }
      void loadHistorySessions()
    }
  }

  const toggleKnowledgeBaseChecked = (
    knowledgeBaseId: string,
    event: MouseEvent<HTMLButtonElement | HTMLInputElement>
  ) => {
    event.stopPropagation()
    setCheckedKnowledgeBaseIds((prev) =>
      prev.includes(knowledgeBaseId)
        ? prev.filter((item) => item !== knowledgeBaseId)
        : [...prev, knowledgeBaseId]
    )
  }

  const toggleDocumentChecked = (
    documentId: string,
    event: MouseEvent<HTMLButtonElement | HTMLInputElement>
  ) => {
    event.stopPropagation()
    setCheckedDocumentIds((prev) =>
      prev.includes(documentId)
        ? prev.filter((item) => item !== documentId)
        : [...prev, documentId]
    )
  }

  const knowledgeBasePageTotal = getPageTotal(
    knowledgeBaseTotal,
    KNOWLEDGE_BASE_PAGE_SIZE
  )
  const documentPageTotal = getPageTotal(documentTotal, DOCUMENT_PAGE_SIZE)
  const documentChunkPageTotal = selectedDocumentDetail
    ? getPageTotal(selectedDocumentDetail.total_chunks, selectedDocumentDetail.page_size)
    : 1
  const visibleChunkTotal = knowledgeBases.reduce((sum, item) => sum + item.chunk_count, 0)
  const chatDisabled = useKnowledgeBase && !selectedKnowledgeBase
  const chatModeLabel = useKnowledgeBase ? '知识库 RAG' : '通用 Agent'
  const mcpStatusLabel = mcpEnabled
    ? useKnowledgeBase
      ? '已启用，但当前 RAG 不使用'
      : savedMcpParseResult.serverSummaries.length > 0
        ? `已启用 ${savedMcpParseResult.serverSummaries.length} 个服务`
        : '已启用'
    : savedMcpParseResult.serverSummaries.length > 0
      ? `已配置 ${savedMcpParseResult.serverSummaries.length} 个服务`
      : '未配置'

  return (
    <div className={styles.container}>
      <div className={styles.backgroundGrid} />
      <div className={styles.backgroundGlow} />

      <div
        className={`${styles.workspaceLayout} ${
          sidebarCollapsed ? styles.workspaceLayoutSidebarCollapsed : ''
        }`}
      >
        <AppSidebar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          viewMode={viewMode}
          knowledgePage={knowledgePage}
          channelPage={channelPage}
          onNavigate={navigateTo}
          historyExpanded={historyExpanded}
          onToggleHistory={() => setHistoryExpanded((expanded) => !expanded)}
          historyLoading={historyLoading}
          historyError={historyError}
          historySessions={historySessions}
          sessionId={sessionId}
          historyLoadingSessionId={historyLoadingSessionId}
          runningThreadIds={runningThreadIds}
          onOpenHistorySession={openHistorySession}
          onDeleteHistorySession={deleteHistorySession}
          channelNavExpanded={channelNavExpanded}
          onChannelsNavClick={handleChannelsNavClick}
          actor={actor}
          accountMenuOpen={accountMenuOpen}
          onAccountMenuOpenChange={setAccountMenuOpen}
          onLogout={handleLogout}
        />

        <main className={styles.mainContent}>
          {viewMode === 'chat' ? (
            <ChatView
              messages={messages}
              sessionId={sessionId}
              userId={currentUserId}
              chatModeLabel={chatModeLabel}
              mcpStatusLabel={mcpStatusLabel}
              status={status}
              isProcessing={isProcessing}
              useKnowledgeBase={useKnowledgeBase}
              selectedKnowledgeBaseName={selectedKnowledgeBase?.name || null}
              showInterrupt={showInterrupt}
              interruptData={interruptData}
              inputValue={inputValue}
              chatDisabled={chatDisabled}
              internetSearch={internetSearch}
              deepThinking={deepThinking}
              currentAssistantMessageId={currentAssistantMessageIdRef.current}
              chatContainerRef={chatContainerRef}
              onChatScroll={handleChatScroll}
              textareaRef={textareaRef}
              toolCallDurations={toolCallDurations}
              onClearChat={clearChat}
              onInterruptAction={handleInterruptAction}
              onAskUserResponse={handleAskUserResponse}
              onInputChange={setInputValue}
              onKeyDown={handleKeyDown}
              onKnowledgeBaseToggle={handleKnowledgeBaseToggle}
              onInternetSearchChange={setInternetSearch}
              onDeepThinkingChange={setDeepThinking}
              onNavigateToKnowledge={() => navigateTo('knowledge', 'libraries')}
              onAbortRequest={abortRequest}
              onSendMessage={sendMessage}
              onRecommendedQuestion={askRecommendedQuestion}
              onRetryMessage={handleRetryMessage}
            />
          ) : viewMode === 'skills' ? (
            <div className={styles.managementViewport}>
              <SkillManagementView
                skills={skills}
                total={skills.length}
                uploadingSkills={uploadingSkills}
                loadingSkills={loadingSkills}
                skillNotice={skillNotice}
                skillError={skillError}
                canManageSkills={actorCapabilities.canManageSkills}
                disabledMessage=""
                uploadInputRef={skillUploadInputRef}
                onOpenUploadDialog={openSkillUploadDialog}
                onUploadSkills={handleUploadSkill}
                onDeleteSkill={deleteSkill}
              />
            </div>
          ) : viewMode === 'mcp' ? (
            <div className={styles.managementViewport}>
              <McpManagementView
                mcpEnabled={mcpEnabled}
                mcpConfigDraft={mcpConfigDraft}
                mcpConfigDirty={mcpConfigDirty}
                mcpNotice={mcpNotice}
                mcpError={mcpError}
                draftError={mcpDraftParseResult.error}
                savedServerCount={savedMcpParseResult.serverSummaries.length}
                draftServerSummaries={mcpDraftParseResult.serverSummaries}
                onMcpConfigDraftChange={setMcpConfigDraft}
                onSaveMcpConfig={saveMcpConfig}
                onFormatMcpConfig={formatMcpConfig}
                onToggleMcpEnabled={toggleMcpEnabled}
                onLoadMcpExample={loadMcpExample}
                onClearMcpConfig={clearMcpConfig}
              />
            </div>
          ) : viewMode === 'channels' ? (
            <div className={styles.managementViewport}>
              <ChannelManagementView
                actor={actor}
                userId={currentUserId}
                channelPage={channelPage}
                requestJson={requestJson}
              />
            </div>
          ) : knowledgePage === 'users' ? (
            <div className={styles.managementViewport}>
              <UserManagementView
                actor={actor}
                users={adminUsers}
                loading={loadingAdminUsers}
                notice={userAdminNotice}
                error={userAdminError}
                onOpenAuth={openLoginPage}
                onLoadUsers={loadAdminUsers}
                onCreateUser={createAdminUser}
                onUpdateUserRole={updateAdminUserRole}
                onUpdateUserStatus={updateAdminUserStatus}
                onResetUserPassword={resetAdminUserPassword}
              />
            </div>
          ) : (
            <div className={styles.managementViewport}>
              <KnowledgeManagementView
                knowledgePage={knowledgePage}
                managementNotice={managementNotice}
                managementError={managementError}
                writeDisabled={!actorCapabilities.canManageKnowledge}
                writeDisabledMessage=""
                knowledgeBaseTotal={knowledgeBaseTotal}
                visibleChunkTotal={visibleChunkTotal}
                knowledgeBases={knowledgeBases}
                selectedKnowledgeBaseId={selectedKnowledgeBaseId}
                selectedKnowledgeBase={selectedKnowledgeBase}
                checkedKnowledgeBaseIds={checkedKnowledgeBaseIds}
                knowledgeBaseSearchInput={knowledgeBaseSearchInput}
                knowledgeBasePage={knowledgeBasePage}
                knowledgeBasePageTotal={knowledgeBasePageTotal}
                documents={documents}
                documentTotal={documentTotal}
                documentPage={documentPage}
                documentPageTotal={documentPageTotal}
                documentSearchInput={documentSearchInput}
                checkedDocumentIds={checkedDocumentIds}
                selectedDocumentDetail={selectedDocumentDetail}
                documentChunkPage={documentChunkPage}
                documentChunkPageTotal={documentChunkPageTotal}
                knowledgeBaseName={knowledgeBaseName}
                knowledgeBaseDescription={knowledgeBaseDescription}
                showCreateKnowledgeBaseModal={showCreateKnowledgeBaseModal}
                savingKnowledgeBase={savingKnowledgeBase}
                uploadingDocuments={uploadingDocuments}
                deletingBulk={deletingBulk}
                loadingDocuments={loadingDocuments}
                loadingDocumentDetail={loadingDocumentDetail}
                uploadInputRef={uploadInputRef}
                onNavigateTo={navigateToKnowledgeView}
                onUpdateKnowledgeBase={updateKnowledgeBase}
                onDeleteKnowledgeBase={deleteKnowledgeBase}
                onOpenUploadDialog={openUploadDialog}
                onHandleUploadFiles={handleUploadFiles}
                onDocumentSearchInputChange={setDocumentSearchInput}
                onDocumentPageChange={setDocumentPage}
                onDocumentSearchChange={setDocumentSearch}
                onBulkDeleteDocuments={bulkDeleteDocuments}
                onToggleDocumentChecked={toggleDocumentChecked}
                onOpenDocumentDetail={openDocumentDetail}
                onRenameDocument={renameDocument}
                onDeleteDocument={deleteDocument}
                onDocumentChunkPageChange={setDocumentChunkPage}
                onKnowledgeBaseSearchInputChange={setKnowledgeBaseSearchInput}
                onKnowledgeBasePageChange={setKnowledgeBasePage}
                onKnowledgeBaseSearchChange={setKnowledgeBaseSearch}
                onBulkDeleteKnowledgeBases={bulkDeleteKnowledgeBases}
                onShowCreateKnowledgeBaseModalChange={setShowCreateKnowledgeBaseModal}
                onToggleKnowledgeBaseChecked={toggleKnowledgeBaseChecked}
                onOpenKnowledgeBaseLibrary={openKnowledgeBaseLibrary}
                onKnowledgeBaseNameChange={setKnowledgeBaseName}
                onKnowledgeBaseDescriptionChange={setKnowledgeBaseDescription}
                onCreateKnowledgeBase={createKnowledgeBase}
              />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
