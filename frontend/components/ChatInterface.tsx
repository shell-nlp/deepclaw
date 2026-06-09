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
import { AccountPanel } from './chat-interface/AccountPanel'
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
import { ChannelManagementView } from './chat-interface/ChannelManagementView'
import { ChatView } from './chat-interface/ChatView'
import {
  AUTH_USERS_CREATE_API_PATH,
  AUTH_USERS_LIST_API_PATH,
  AUTH_USERS_RESET_PASSWORD_API_PATH,
  AUTH_USERS_UPDATE_ROLE_API_PATH,
  AUTH_USERS_UPDATE_STATUS_API_PATH,
  DEFAULT_AGENT_API_PATH,
  DEFAULT_KNOWLEDGE_PAGE,
  DEFAULT_MCP_CONFIG_TEMPLATE,
  DEFAULT_RAG_API_PATH,
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
import { KnowledgeManagementView } from './chat-interface/KnowledgeManagementView'
import { McpManagementView } from './chat-interface/McpManagementView'
import { SkillManagementView } from './chat-interface/SkillManagementView'
import type {
  AssistantMessageItem,
  AuthLoginResponse,
  AuthUserListResponse,
  AuthUserSummary,
  BulkDeleteDocumentResponse,
  BulkDeleteKnowledgeBaseResponse,
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
  StreamEvent,
  UploadResult,
  ViewMode,
} from './chat-interface/types'
import { UserManagementView } from './chat-interface/UserManagementView'
import {
  createClearedChatState,
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
  const [knowledgePage, setKnowledgePage] =
    useState<KnowledgePage>(DEFAULT_KNOWLEDGE_PAGE)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [status, setStatus] = useState<'ready' | 'connecting' | 'error'>('ready')
  const [isProcessing, setIsProcessing] = useState(false)
  const [internetSearch, setInternetSearch] = useState(false)
  const [deepThinking, setDeepThinking] = useState(false)
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(false)
  const [showInterrupt, setShowInterrupt] = useState(false)
  const [interruptData, setInterruptData] = useState<InterruptData | null>(null)

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
  const [selectedKnowledgeBaseName, setSelectedKnowledgeBaseName] = useState('')
  const [selectedKnowledgeBaseDescription, setSelectedKnowledgeBaseDescription] =
    useState('')
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
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const skillUploadInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const currentAssistantMessageIdRef = useRef<string | null>(null)
  const processedToolCallIdsRef = useRef<Set<string>>(new Set())
  const lastAssistantStreamEventRef = useRef<
    'reasoning' | 'content' | 'tool' | 'interrupt' | null
  >(null)
  const reasoningBlockCounterRef = useRef(0)
  const contentBlockCounterRef = useRef(0)
  const requestModeRef = useRef<RequestMode>('agent')
  const requestKnowledgeBaseRef = useRef<KnowledgeBase | null>(null)
  const requestMcpConfigRef = useRef<Record<string, unknown> | null>(null)

  const actorCapabilities = getActorCapabilities(actor)
  const currentUserId = actor.userId || GUEST_USER_ID
  const guestKnowledgeMessage =
    '游客可浏览知识库内容，登录后可创建、上传和管理知识库。请点击右上角头像登录。'
  const guestSkillMessage =
    '游客可查看技能列表，登录后可上传或删除技能。请点击右上角头像登录。'
  const mcpDraftParseResult = parseMcpConfig(mcpConfigDraft)
  const savedMcpParseResult = parseMcpConfig(savedMcpConfigText)
  const mcpConfigDirty = mcpConfigDraft !== savedMcpConfigText

  const scrollToBottom = useCallback(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [])

  const clearChat = useCallback(() => {
    const clearedState = createClearedChatState()
    setMessages([])
    setShowInterrupt(clearedState.showInterrupt)
    setInterruptData(clearedState.interruptData)
    currentAssistantMessageIdRef.current = null
    processedToolCallIdsRef.current.clear()
    lastAssistantStreamEventRef.current = null
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    requestModeRef.current = 'agent'
    requestKnowledgeBaseRef.current = null
    requestMcpConfigRef.current = null
    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_chat_session_id', clearedState.sessionId)
    }
    setSessionId(clearedState.sessionId)
  }, [])

  const resetUserScopedState = useCallback(() => {
    setKnowledgeBasePage(1)
    setKnowledgeBaseSearch('')
    setKnowledgeBaseSearchInput('')
    setSelectedKnowledgeBaseId('')
    setSelectedKnowledgeBase(null)
    setSelectedKnowledgeBaseName('')
    setSelectedKnowledgeBaseDescription('')
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
    clearChat()
  }, [clearChat])

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

  const requestStreamResponse = useCallback(
    async (path: string, payload: Record<string, unknown>, signal?: AbortSignal) => {
      const response = await fetch(getApiUrl(path), {
        method: 'POST',
        headers: withAuthHeaders({
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        }),
        body: JSON.stringify(payload),
        signal,
      })

      if (!response.ok) {
        let message = `HTTP ${response.status}`
        try {
          const errorPayload = await response.json()
          if (errorPayload?.detail) {
            message = String(errorPayload.detail)
          }
        } catch {
          // ignore parse error
        }
        if (isUnauthorizedErrorMessage(message)) {
          clearAuthState('登录状态已失效，已切换为游客模式。')
        }
        throw new Error(message)
      }

      return response
    },
    [clearAuthState, withAuthHeaders]
  )

  const addMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      const existing = prev.find((item) => item.id === message.id)
      if (existing) {
        return prev.map((item) =>
          item.id === message.id ? { ...item, ...message } : item
        )
      }
      return [...prev, message]
    })
  }, [])

  const ensureAssistantMessage = useCallback(() => {
    let assistantMessageId = currentAssistantMessageIdRef.current
    if (!assistantMessageId) {
      assistantMessageId = generateMessageId()
      currentAssistantMessageIdRef.current = assistantMessageId
      addMessage({ id: assistantMessageId, role: 'ai', content: '', toolData: [] })
    }
    return assistantMessageId
  }, [addMessage])

  const updateAssistantMessage = useCallback(
    (updater: (message: Message) => Message) => {
      const assistantMessageId = ensureAssistantMessage()
      setMessages((prev) =>
        prev.map((item) => (item.id === assistantMessageId ? updater(item) : item))
      )
    },
    [ensureAssistantMessage]
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

    setSessionId(freshSessionId)
    setMcpConfigDraft(storedMcpConfig)
    setSavedMcpConfigText(storedMcpConfig)
    setMcpConfig(parsedMcpConfig.config)
    setMcpEnabled(Boolean(parsedMcpConfig.config) && storedMcpEnabled)

    if (storedMcpConfig && parsedMcpConfig.error) {
      setMcpError(`本地保存的 MCP 配置无效：${parsedMcpConfig.error}`)
    }

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
  }, [applyActorState, clearAuthState])

  const navigateTo = useCallback(
    (
      nextViewMode: ViewMode,
      nextKnowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE,
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

      if (typeof window === 'undefined') return
      const nextHash = getRouteHash(nextViewMode, safeKnowledgePage)
      if (window.location.hash === nextHash) return

      if (replace) {
        window.history.replaceState(null, '', nextHash)
      } else {
        window.history.pushState(null, '', nextHash)
      }
    },
    [selectedKnowledgeBase]
  )

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

      const expectedHash = getRouteHash(route.viewMode, safeKnowledgePage)
      if (window.location.hash !== expectedHash) {
        window.history.replaceState(null, '', expectedHash)
      }
    }

    if (!window.location.hash) {
      window.history.replaceState(null, '', getRouteHash('chat'))
    }

    syncRoute()
    window.addEventListener('hashchange', syncRoute)
    return () => window.removeEventListener('hashchange', syncRoute)
  }, [selectedKnowledgeBase])

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
            setSelectedKnowledgeBaseName(matched.name)
            setSelectedKnowledgeBaseDescription(matched.description)
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
        setSelectedKnowledgeBaseName(result.name)
        setSelectedKnowledgeBaseDescription(result.description)
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
      setSelectedKnowledgeBaseName(knowledgeBase.name)
      setSelectedKnowledgeBaseDescription(knowledgeBase.description)
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

  const saveKnowledgeBase = async () => {
    if (!selectedKnowledgeBase) return

    setSavingKnowledgeBase(true)
    setManagementError('')
    setManagementNotice('')
    try {
      const updated = await requestJson<KnowledgeBase>(KB_UPDATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
          name: selectedKnowledgeBaseName.trim(),
          description: selectedKnowledgeBaseDescription.trim(),
        }),
      })
      await loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
      selectKnowledgeBase(updated)
      setManagementNotice(`知识库 "${updated.name}" 已更新。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '更新知识库失败。')
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
        setSelectedKnowledgeBaseName('')
        setSelectedKnowledgeBaseDescription('')
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
        setSelectedKnowledgeBaseName('')
        setSelectedKnowledgeBaseDescription('')
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

  const handleStreamEvent = useCallback(
    (event: StreamEvent): StreamEvent['event'] | null => {
      const data = event.data
      if (!data) return null

      switch (event.event) {
        case 'token': {
          if (data.reasoning_token) {
            const shouldStartNewBlock =
              lastAssistantStreamEventRef.current !== 'reasoning'
            updateAssistantMessage((message) => {
              const { reasoningBlocks, messageItems } = appendReasoningToken(
                message.reasoningBlocks,
                message.messageItems,
                data.reasoning_token || '',
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
                reasoningContent: `${message.reasoningContent || ''}${data.reasoning_token}`,
              }
            })
            lastAssistantStreamEventRef.current = 'reasoning'
          }

          if (data.token) {
            const shouldAppendToLastBlock =
              lastAssistantStreamEventRef.current === 'content'
            updateAssistantMessage((message) => {
              const { contentBlocks, messageItems } = appendContentToken(
                message.contentBlocks,
                message.messageItems,
                data.token || '',
                shouldAppendToLastBlock,
                () => {
                  contentBlockCounterRef.current += 1
                  return `${message.id}_content_${contentBlockCounterRef.current}`
                }
              )

              return {
                ...message,
                content: `${message.content}${data.token}`,
                contentBlocks,
                messageItems,
              }
            })
            lastAssistantStreamEventRef.current = 'content'
          }
          break
        }

        case 'tool_calls': {
          if (data.tool_calls?.length) {
            updateAssistantMessage((message) => {
              const tools = [...(message.toolData || [])]
              let messageItems = message.messageItems || []
              for (const toolCall of data.tool_calls || []) {
                if (!tools.some((tool) => tool.toolCall.id === toolCall.id)) {
                  tools.push({ toolCall, toolOutput: [] })
                }
                messageItems = ensureToolItem(messageItems, toolCall.id)
              }
              return { ...message, toolData: tools, messageItems }
            })
            lastAssistantStreamEventRef.current = 'tool'
          }
          break
        }

        case 'tool_output': {
          if (data.tool_output?.length) {
            updateAssistantMessage((message) => {
              let tools = [...(message.toolData || [])]
              let messageItems = message.messageItems || []

              for (const output of data.tool_output || []) {
                if (processedToolCallIdsRef.current.has(output.tool_call_id)) {
                  continue
                }
                processedToolCallIdsRef.current.add(output.tool_call_id)

                const normalizedOutput = {
                  ...output,
                  content: stringifyToolContent(output.content),
                }
                const existingToolIndex = tools.findIndex(
                  (tool) => tool.toolCall.id === output.tool_call_id
                )

                if (existingToolIndex >= 0) {
                  const existingTool = tools[existingToolIndex]
                  tools = tools.map((tool, index) =>
                    index === existingToolIndex
                      ? {
                          ...existingTool,
                          toolOutput: [
                            ...(existingTool.toolOutput || []),
                            normalizedOutput,
                          ],
                        }
                      : tool
                  )
                } else {
                  tools.push({
                    toolCall: {
                      id: output.tool_call_id,
                      name: 'tool',
                      args: {},
                    },
                    toolOutput: [normalizedOutput],
                  })
                }
                messageItems = ensureToolItem(messageItems, output.tool_call_id)
              }

              return { ...message, toolData: tools, messageItems }
            })
            lastAssistantStreamEventRef.current = 'tool'
          }
          break
        }

        case '__interrupt__': {
          if (data.__interrupt__) {
            setInterruptData(data.__interrupt__)
            setShowInterrupt(true)
            setIsProcessing(false)
            setStatus('ready')
            lastAssistantStreamEventRef.current = 'interrupt'
          }
          break
        }
      }

      return event.event
    },
    [updateAssistantMessage]
  )

  const readEventStream = useCallback(
    async (response: Response) => {
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let interrupted = false

      const processChunk = (chunk: string) => {
        const normalized = chunk.replace(/\r\n/g, '\n')
        const parts = normalized.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const dataLines = part
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trim())

          if (dataLines.length === 0) continue

          try {
            const handledEvent = handleStreamEvent(
              JSON.parse(dataLines.join('\n')) as StreamEvent
            )
            if (handledEvent === '__interrupt__') {
              interrupted = true
            }
          } catch (error) {
            console.error('Parse error:', error, dataLines.join('\n'))
          }
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        processChunk(buffer)
      }

      buffer += decoder.decode()
      if (buffer.trim()) {
        processChunk(`${buffer}\n\n`)
      }

      return { interrupted }
    },
    [handleStreamEvent]
  )

  const sendMessage = async () => {
    const query = inputValue.trim()
    if (!query || isProcessing || !sessionId) return

    const requestMode: RequestMode = useKnowledgeBase ? 'rag' : 'agent'
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

    addMessage({
      id: generateMessageId(),
      role: 'user',
      content: query,
    })
    setInputValue('')

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    setIsProcessing(true)
    setStatus('connecting')

    const assistantMessageId = generateMessageId()
    currentAssistantMessageIdRef.current = assistantMessageId
    processedToolCallIdsRef.current.clear()
    lastAssistantStreamEventRef.current = null
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    requestModeRef.current = requestMode
    requestKnowledgeBaseRef.current = selectedKnowledgeBase
    requestMcpConfigRef.current = requestMcpConfig
    addMessage({ id: assistantMessageId, role: 'ai', content: '', toolData: [] })

    abortControllerRef.current = new AbortController()

    try {
      const payload: Record<string, unknown> = {
        query,
        session_id: sessionId,
        user_id: currentUserId,
        internet_search: internetSearch,
        deep_thinking: deepThinking,
      }
      if (requestMode === 'rag' && selectedKnowledgeBase) {
        payload.index_name = selectedKnowledgeBase.passage_index
        payload.graph_name = selectedKnowledgeBase.index_prefix
      } else if (requestMode === 'agent' && requestMcpConfig) {
        payload.mcp_config = requestMcpConfig
      }

      const response = await requestStreamResponse(
        requestMode === 'rag' ? DEFAULT_RAG_API_PATH : DEFAULT_AGENT_API_PATH,
        payload,
        abortControllerRef.current.signal
      )
      await readEventStream(response)
      setStatus('ready')
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        setStatus('error')
        addMessage({
          id: generateMessageId(),
          role: 'ai',
          content: `Request failed: ${error.message}`,
        })
      } else {
        setStatus('ready')
      }
    } finally {
      setIsProcessing(false)
      currentAssistantMessageIdRef.current = null
      processedToolCallIdsRef.current.clear()
      lastAssistantStreamEventRef.current = null
      reasoningBlockCounterRef.current = 0
      contentBlockCounterRef.current = 0
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  const abortRequest = () => {
    abortControllerRef.current?.abort()
  }

  const handleInterruptAction = async (
    decision: 'approve' | 'reject' | 'edit',
    editedActions?: Array<{ name: string; args: Record<string, unknown> }>
  ) => {
    if (!interruptData) return

    const requestMode = requestModeRef.current
    const requestKnowledgeBase = requestKnowledgeBaseRef.current
    const requestMcpConfig = requestMcpConfigRef.current
    if (requestMode === 'rag' && !requestKnowledgeBase) {
      setManagementError('当前中断来自知识库问答，但未找到对应知识库，请重新发起请求。')
      setShowInterrupt(false)
      setInterruptData(null)
      return
    }

    setShowInterrupt(false)
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

    setIsProcessing(true)
    setStatus('connecting')
    lastAssistantStreamEventRef.current = null
    reasoningBlockCounterRef.current = 0
    contentBlockCounterRef.current = 0
    abortControllerRef.current = new AbortController()
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

      const payload: Record<string, unknown> = {
        resume: { decisions },
        session_id: sessionId,
        user_id: currentUserId,
      }
      if (requestMode === 'rag' && requestKnowledgeBase) {
        payload.index_name = requestKnowledgeBase.passage_index
        payload.graph_name = requestKnowledgeBase.index_prefix
      } else if (requestMode === 'agent' && requestMcpConfig) {
        payload.mcp_config = requestMcpConfig
      }

      const response = await requestStreamResponse(
        requestMode === 'rag' ? DEFAULT_RAG_API_PATH : DEFAULT_AGENT_API_PATH,
        payload,
        abortControllerRef.current.signal
      )
      const streamResult = await readEventStream(response)
      receivedInterrupt = streamResult.interrupted
      setStatus('ready')
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        setStatus('error')
        addMessage({
          id: generateMessageId(),
          role: 'ai',
          content: `Resume failed: ${error.message}`,
        })
      }
    } finally {
      setIsProcessing(false)
      if (!receivedInterrupt) {
        setInterruptData(null)
      }
      currentAssistantMessageIdRef.current = null
      processedToolCallIdsRef.current.clear()
      lastAssistantStreamEventRef.current = null
      reasoningBlockCounterRef.current = 0
      contentBlockCounterRef.current = 0
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

      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.logoArea}>
            <span className={styles.logoIcon}>AI</span>
            <div>
              <h1 className={styles.title}>DeepClaw</h1>
              <p className={styles.subtitle}>
                智能问答 · MCP 工具接入 · 知识库管理 · 图检索 RAG
              </p>
            </div>
          </div>
          <AccountPanel
            actor={actor}
            open={accountMenuOpen}
            onOpenChange={setAccountMenuOpen}
            onLogout={handleLogout}
          />
        </div>
      </header>

      <div className={styles.workspaceLayout}>
        <aside className={styles.sidebarNav}>
          <div className={styles.sidebarPanel}>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'chat' ? styles.sidebarButtonActive : ''
              }`}
              onClick={() => navigateTo('chat')}
            >
              聊天
            </button>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'knowledge' && knowledgePage !== 'users'
                  ? styles.sidebarButtonActive
                  : ''
              }`}
              onClick={() => navigateTo('knowledge', 'libraries')}
            >
              知识库
            </button>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'skills' ? styles.sidebarButtonActive : ''
              }`}
              onClick={() => navigateTo('skills')}
            >
              技能管理
            </button>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'mcp' ? styles.sidebarButtonActive : ''
              }`}
              onClick={() => navigateTo('mcp')}
            >
              MCP 管理
            </button>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'channels' ? styles.sidebarButtonActive : ''
              }`}
              onClick={() => navigateTo('channels')}
            >
              渠道管理
            </button>
            <button
              className={`${styles.sidebarButton} ${
                viewMode === 'knowledge' && knowledgePage === 'users'
                  ? styles.sidebarButtonActive
                  : ''
              }`}
              onClick={() => navigateTo('knowledge', 'users')}
            >
              用户管理
            </button>
          </div>
        </aside>

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
              textareaRef={textareaRef}
              onClearChat={clearChat}
              onInterruptAction={handleInterruptAction}
              onInputChange={setInputValue}
              onKeyDown={handleKeyDown}
              onKnowledgeBaseToggle={handleKnowledgeBaseToggle}
              onInternetSearchChange={setInternetSearch}
              onDeepThinkingChange={setDeepThinking}
              onNavigateToKnowledge={() => navigateTo('knowledge', 'libraries')}
              onAbortRequest={abortRequest}
              onSendMessage={sendMessage}
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
                disabledMessage={guestSkillMessage}
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
                writeDisabledMessage={guestKnowledgeMessage}
                knowledgeBaseTotal={knowledgeBaseTotal}
                visibleChunkTotal={visibleChunkTotal}
                knowledgeBases={knowledgeBases}
                selectedKnowledgeBaseId={selectedKnowledgeBaseId}
                selectedKnowledgeBase={selectedKnowledgeBase}
                selectedKnowledgeBaseName={selectedKnowledgeBaseName}
                selectedKnowledgeBaseDescription={selectedKnowledgeBaseDescription}
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
                onNavigateTo={navigateTo}
                onSelectedKnowledgeBaseNameChange={setSelectedKnowledgeBaseName}
                onSelectedKnowledgeBaseDescriptionChange={
                  setSelectedKnowledgeBaseDescription
                }
                onSaveKnowledgeBase={saveKnowledgeBase}
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
