'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchCurrentActor, getStoredAuthToken } from '../utils/auth'
import {
  AGUI_AGENTS_API_PATH,
  DEFAULT_AGUI_API_PATH,
  RUNTIME_CONFIG_API_PATH,
} from '../utils/constants'
import { generateMessageId, generateSessionId, getApiUrl } from '../utils'
import {
  createThreadRuntime,
  toChatError,
  type ThreadRuntime,
} from '../utils/chatRuntime'
import type {
  AgentListResponse,
  AgentSummary,
  InterruptData,
  KnowledgeBase,
  Message,
  RequestMode,
} from '../utils/types'
import { useMcpConfig } from './useMcpConfig'
import { useSkills } from './useSkills'
import { useAuthSession } from './useAuthSession'
import { useKnowledgeManagement } from './useKnowledgeManagement'
import { useChatRuntime } from './useChatRuntime'
import { usePageRouting } from './usePageRouting'
import { useHistorySessions } from './useHistorySessions'

export function useChatPageController() {
  const selectedKnowledgeBaseRef = useRef<KnowledgeBase | null>(null)
  const routing = usePageRouting(selectedKnowledgeBaseRef)
  const {
    viewMode,
    setViewMode,
    channelPage,
    channelNavExpanded,
    sidebarCollapsed,
    knowledgePage,
    setKnowledgePage,
    navigateTo,
    handleChannelsNavClick,
    toggleSidebar,
    navigateToKnowledgeView,
  } = routing

  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [status, setStatus] = useState<'ready' | 'connecting' | 'error'>('ready')
  const [aguiApiPath, setAguiApiPath] = useState(DEFAULT_AGUI_API_PATH)
  const [availableAgents, setAvailableAgents] = useState<AgentSummary[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [runningThreadIds, setRunningThreadIds] = useState<string[]>([])
  const [internetSearch, setInternetSearch] = useState(false)
  const [deepThinking, setDeepThinking] = useState(true)
  const [isKnowledgeMode, setIsKnowledgeMode] = useState(false)
  const [showInterrupt, setShowInterrupt] = useState(false)
  const [interruptData, setInterruptData] = useState<InterruptData | null>(null)
  const [toolCallDurations, setToolCallDurations] = useState<Record<string, number>>({})
  const {
    mcpConfigDraft,
    setMcpConfigDraft,
    mcpConfig,
    mcpEnabled,
    mcpNotice,
    mcpError,
    mcpDraftParseResult,
    savedMcpParseResult,
    mcpConfigDirty,
    initializeMcpConfig,
    saveMcpConfig,
    formatMcpConfig,
    toggleMcpEnabled,
    loadMcpExample,
    clearMcpConfig,
    mcpStatusLabel,
  } = useMcpConfig(viewMode, isKnowledgeMode)





  const [managementError, setManagementError] = useState('')
  const [managementNotice, setManagementNotice] = useState('')
  const resetUserScopedStateRef = useRef<() => void>(() => {})
  const resetKnowledgeStateRef = useRef<() => void>(() => {})
  const {
    actor,
    setAuthToken,
    accountMenuOpen,
    setAccountMenuOpen,
    adminUsers,
    setAdminUsers,
    loadingAdminUsers,
    userAdminNotice,
    userAdminError,
    actorCapabilities,
    currentUserId,
    applyActorState,
    clearAuthState,
    withAuthHeaders,
    requestJson,
    loadAdminUsers,
    handleLogout,
    openLoginPage,
    createAdminUser,
    updateAdminUserRole,
    updateAdminUserStatus,
    resetAdminUserPassword,
  } = useAuthSession({
    onActorChange: () => resetUserScopedStateRef.current(),
    setManagementNotice,
  })

  const chatContainerRef = useRef<HTMLDivElement>(null)
  const isChatAtBottomRef = useRef(true)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
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
    resetKnowledgeStateRef.current()
    setAdminUsers([])
    resetAllRuntimesAndChat()
  }, [resetAllRuntimesAndChat])

  resetUserScopedStateRef.current = resetUserScopedState

  const {
    skills,
    loadingSkills,
    uploadingSkills,
    skillNotice,
    skillError,
    skillUploadInputRef,
    openSkillUploadDialog,
    handleUploadSkill,
    deleteSkill,
  } = useSkills(requestJson)

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

    localStorage.setItem('rag_chat_session_id', freshSessionId)
    activeThreadIdRef.current = freshSessionId
    messagesRef.current = []
    setSessionId(freshSessionId)
    getThreadRuntime(freshSessionId)
    initializeMcpConfig(storedMcpConfig, storedMcpEnabled)

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





  /**
   * 切换侧边导航的展开状态，为聊天主区域腾出更多空间。
   *
   * Args:
   * - 无。
   */




  const history = useHistorySessions({
    requestJson,
    sessionId,
    runningThreadIds,
    switchToThreadRef,
    navigateTo,
    scrollToBottom,
    threadRuntimesRef,
    setThreadRunning,
    streamGenerationRef,
    abortControllerRef,
    resetActiveChatView,
    getThreadRuntime,
  })
  const {
    historySessions,
    historyExpanded,
    setHistoryExpanded,
    historyLoading,
    historyLoadingSessionId,
    historyError,
    loadHistorySessions,
    openHistorySession,
    deleteHistorySession,
  } = history
  const knowledge = useKnowledgeManagement({
    requestJson,
    currentUserId,
    availableAgents,
    isKnowledgeMode,
    setIsKnowledgeMode,
    clearChat,
    navigateTo,
    setViewMode,
    setKnowledgePage,
    setManagementNotice,
    setManagementError,
    knowledgePage,
    channelPage,
    requestKnowledgeBaseRef,
    requestModeRef,
    setShowInterrupt,
    setInterruptData,
  })
  const {
    selectedKnowledgeBaseIds,
    knowledgeBaseOptions,
    knowledgePickerOpen,
    loadingKnowledgeBaseOptions,
    knowledgeBases,
    knowledgeBaseTotal,
    knowledgeBasePage,
    setKnowledgeBasePage,
    knowledgeBaseSearchInput,
    setKnowledgeBaseSearchInput,
    setKnowledgeBaseSearch,
    selectedKnowledgeBaseId,
    selectedKnowledgeBase,
    checkedKnowledgeBaseIds,
    documents,
    uploadTasks,
    documentTotal,
    documentPage,
    setDocumentPage,
    documentSearchInput,
    setDocumentSearchInput,
    setDocumentSearch,
    checkedDocumentIds,
    selectedDocumentDetail,
    documentChunkPage,
    setDocumentChunkPage,
    loadingDocumentDetail,
    knowledgeBaseName,
    setKnowledgeBaseName,
    knowledgeBaseDescription,
    setKnowledgeBaseDescription,
    showCreateKnowledgeBaseModal,
    setShowCreateKnowledgeBaseModal,
    loadingDocuments,
    savingKnowledgeBase,
    uploadingDocuments,
    deletingBulk,
    uploadInputRef,
    handleKnowledgePickerOpenChange,
    handleKnowledgeSelectionChange,
    chatModeOptions,
    activeChatModeId,
    handleChatModeChange,
    knowledgeIndexNames,
    primaryKnowledgeBase,
    openKnowledgeBaseLibrary,
    openDocumentDetail,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    bulkDeleteKnowledgeBases,
    openUploadDialog,
    handleUploadFiles,
    retryUploadTask,
    deleteUploadTask,
    updateDocumentChunk,
    renameDocument,
    deleteDocument,
    bulkDeleteDocuments,
    toggleKnowledgeBaseChecked,
    toggleDocumentChecked,
    knowledgeBasePageTotal,
    documentPageTotal,
    documentChunkPageTotal,
    visibleChunkTotal,
  } = knowledge
  selectedKnowledgeBaseRef.current = knowledge.selectedKnowledgeBase
  resetKnowledgeStateRef.current = knowledge.resetKnowledgeState
  useEffect(() => {
    scrollToBottom()
  }, [messages, showInterrupt, interruptData, scrollToBottom])


  /**
   * 将当前思考块的耗时写入对应的消息块。
   *
   * Args:
   * - 无。
   */

  const runtime = useChatRuntime({
    messages,
    inputValue,
    setInputValue,
    sessionId,
    setSessionId,
    status,
    setStatus,
    isProcessing,
    setIsProcessing,
    runningThreadIds,
    setRunningThreadIds,
    internetSearch,
    deepThinking,
    showInterrupt,
    setShowInterrupt,
    interruptData,
    setInterruptData,
    toolCallDurations,
    setToolCallDurations,
    availableAgents,
    aguiApiPath,
    abortControllerRef,
    activeThreadIdRef,
    threadRuntimesRef,
    messagesRef,
    streamGenerationRef,
    switchToThreadRef,
    currentRunIdRef,
    currentRunInputRef,
    lastEventIdRef,
    toolCallArgsRef,
    currentAssistantMessageIdRef,
    processedToolCallIdsRef,
    lastAssistantStreamEventRef,
    reasoningStartTimeRef,
    toolCallStartTimesRef,
    reasoningBlockCounterRef,
    contentBlockCounterRef,
    requestModeRef,
    requestKnowledgeBaseRef,
    requestMcpConfigRef,
    retryActionsRef,
    setMessagesAndRef,
    setThreadRunning,
    getThreadRuntime,
    syncRuntimeToRefs,
    syncRuntimeToView,
    persistActiveRuntime,
    resetActiveChatView,
    scrollToBottom,
    addMessage,
    ensureAssistantMessage,
    updateAssistantMessage,
    applyAssistantError,
    registerRetryAction,
    requestJson,
    withAuthHeaders,
    navigateTo,
    knowledgeIndexNames,
    primaryKnowledgeBase,
    mcpConfig,
    mcpEnabled,
    activeChatModeId,
    setManagementError,
    textareaRef,
    loadHistorySessions,
  })
  const {
    sendMessage,
    handleKeyDown,
    askRecommendedQuestion,
    abortRequest,
    handleInterruptAction,
    handleAskUserResponse,
  } = runtime
  const chatDisabled = isKnowledgeMode && knowledgeIndexNames.length === 0
  return {
    viewMode,
    channelPage,
    channelNavExpanded,
    sidebarCollapsed,
    knowledgePage,
    messages,
    inputValue,
    setInputValue,
    sessionId,
    historySessions,
    historyExpanded,
    setHistoryExpanded,
    historyLoading,
    historyLoadingSessionId,
    historyError,
    status,
    isProcessing,
    runningThreadIds,
    internetSearch,
    setInternetSearch,
    deepThinking,
    setDeepThinking,
    isKnowledgeMode,
    selectedKnowledgeBaseIds,
    knowledgeBaseOptions,
    knowledgePickerOpen,
    loadingKnowledgeBaseOptions,
    showInterrupt,
    interruptData,
    toolCallDurations,
    actor,
    accountMenuOpen,
    setAccountMenuOpen,
    adminUsers,
    loadingAdminUsers,
    userAdminNotice,
    userAdminError,
    knowledgeBases,
    knowledgeBaseTotal,
    knowledgeBasePage,
    setKnowledgeBasePage,
    knowledgeBaseSearchInput,
    setKnowledgeBaseSearchInput,
    setKnowledgeBaseSearch,
    selectedKnowledgeBaseId,
    selectedKnowledgeBase,
    checkedKnowledgeBaseIds,
    documents,
    uploadTasks,
    documentTotal,
    documentPage,
    setDocumentPage,
    documentSearchInput,
    setDocumentSearchInput,
    setDocumentSearch,
    checkedDocumentIds,
    selectedDocumentDetail,
    documentChunkPage,
    setDocumentChunkPage,
    loadingDocumentDetail,
    knowledgeBaseName,
    setKnowledgeBaseName,
    knowledgeBaseDescription,
    setKnowledgeBaseDescription,
    showCreateKnowledgeBaseModal,
    setShowCreateKnowledgeBaseModal,
    mcpConfigDraft,
    setMcpConfigDraft,
    mcpEnabled,
    mcpNotice,
    mcpError,
    skills,
    loadingSkills,
    uploadingSkills,
    skillNotice,
    skillError,
    managementError,
    managementNotice,
    loadingDocuments,
    savingKnowledgeBase,
    uploadingDocuments,
    deletingBulk,
    chatContainerRef,
    textareaRef,
    uploadInputRef,
    skillUploadInputRef,
    currentAssistantMessageIdRef,
    actorCapabilities,
    currentUserId,
    mcpDraftParseResult,
    savedMcpParseResult,
    mcpConfigDirty,
    handleChatScroll,
    clearChat,
    requestJson,
    handleRetryMessage,
    navigateTo,
    openHistorySession,
    deleteHistorySession,
    handleChannelsNavClick,
    toggleSidebar,
    navigateToKnowledgeView,
    loadAdminUsers,
    handleKnowledgePickerOpenChange,
    handleKnowledgeSelectionChange,
    chatModeOptions,
    activeChatModeId,
    handleChatModeChange,
    saveMcpConfig,
    formatMcpConfig,
    toggleMcpEnabled,
    loadMcpExample,
    clearMcpConfig,
    handleLogout,
    openLoginPage,
    createAdminUser,
    updateAdminUserRole,
    updateAdminUserStatus,
    resetAdminUserPassword,
    openSkillUploadDialog,
    handleUploadSkill,
    deleteSkill,
    openKnowledgeBaseLibrary,
    openDocumentDetail,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    bulkDeleteKnowledgeBases,
    openUploadDialog,
    handleUploadFiles,
    retryUploadTask,
    deleteUploadTask,
    updateDocumentChunk,
    renameDocument,
    deleteDocument,
    bulkDeleteDocuments,
    sendMessage,
    handleKeyDown,
    askRecommendedQuestion,
    abortRequest,
    handleInterruptAction,
    handleAskUserResponse,
    toggleKnowledgeBaseChecked,
    toggleDocumentChecked,
    knowledgeBasePageTotal,
    documentPageTotal,
    documentChunkPageTotal,
    visibleChunkTotal,
    chatDisabled,
    mcpStatusLabel,
  }
}
