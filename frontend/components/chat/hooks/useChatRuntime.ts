'use client'

import {
  ChangeEvent,
  KeyboardEvent,
  MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { Dispatch, MutableRefObject, SetStateAction } from 'react'

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
} from '../utils/auth'
import {
  createAgUiRunInput,
  getAgUiInterrupt,
  getAgUiInterruptOutcome,
  getAgUiAssistantSnapshotText,
  getLatestAssistantTokenUsage,
  getRecommendedQuestions,
  getTokenUsageFromMessage,
  parseAgUiSseFrame,
  type AgUiEvent,
  type AgUiInterrupt,
} from '../utils/agui'
import { resolveChannelEntryPage } from '../utils/channelManagement'
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
  KB_DOCUMENT_UPLOAD_TASK_DELETE_API_PATH,
  KB_DOCUMENT_UPLOAD_TASK_RETRY_API_PATH,
  KB_DOCUMENT_CHUNK_UPDATE_API_PATH,
  KB_DOCUMENT_UPLOAD_TASKS_API_PATH,
  KB_LIST_API_PATH,
  KB_UPDATE_API_PATH,
  KNOWLEDGE_BASE_OPTION_PAGE_SIZE,
  KNOWLEDGE_BASE_PAGE_SIZE,
  GENERAL_AGENT_ID,
  KNOWLEDGE_AGENT_CAPABILITY,
  KNOWLEDGE_AGENT_ID,
  SKILL_DELETE_API_PATH,
  SKILL_LIST_API_PATH,
  SKILL_UPLOAD_API_PATH,
} from '../utils/constants'
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
  ChatModeOption,
  ChatStatus,
  InterruptData,
  KnowledgeBase,
  KnowledgeChunk,
  KnowledgeDocument,
  KnowledgeDocumentDetailResponse,
  KnowledgeUploadTask,
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
} from '../utils/types'
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
} from '../utils'
import {
  ChatRequestError,
  appendContentToken,
  appendReasoningToken,
  createChatError,
  createHttpChatError,
  createThreadRuntime,
  ensureToolItem,
  isAbortError,
  isActiveRunStatus,
  toChatError,
  toHistoryMessages,
  type AssistantStreamKind,
  type ResumeDecision,
  type ThreadRuntime,
} from '../utils/chatRuntime'

type UseChatRuntimeDeps = {
  messages: Message[]
  inputValue: string
  setInputValue: Dispatch<SetStateAction<string>>
  sessionId: string
  setSessionId: Dispatch<SetStateAction<string>>
  status: ChatStatus
  setStatus: Dispatch<SetStateAction<ChatStatus>>
  isProcessing: boolean
  setIsProcessing: Dispatch<SetStateAction<boolean>>
  runningThreadIds: string[]
  setRunningThreadIds: Dispatch<SetStateAction<string[]>>
  internetSearch: boolean
  deepThinking: boolean
  showInterrupt: boolean
  setShowInterrupt: Dispatch<SetStateAction<boolean>>
  interruptData: InterruptData | null
  setInterruptData: Dispatch<SetStateAction<InterruptData | null>>
  toolCallDurations: Record<string, number>
  setToolCallDurations: Dispatch<SetStateAction<Record<string, number>>>
  availableAgents: AgentSummary[]
  aguiApiPath: string
  abortControllerRef: MutableRefObject<AbortController | null>
  activeThreadIdRef: MutableRefObject<string>
  threadRuntimesRef: MutableRefObject<Map<string, ThreadRuntime>>
  messagesRef: MutableRefObject<Message[]>
  streamGenerationRef: MutableRefObject<number>
  switchToThreadRef: MutableRefObject<(threadId: string) => Promise<void>>
  currentRunIdRef: MutableRefObject<string | null>
  currentRunInputRef: MutableRefObject<Record<string, unknown> | null>
  lastEventIdRef: MutableRefObject<string | null>
  toolCallArgsRef: MutableRefObject<Record<string, string>>
  currentAssistantMessageIdRef: MutableRefObject<string | null>
  processedToolCallIdsRef: MutableRefObject<Set<string>>
  lastAssistantStreamEventRef: MutableRefObject<AssistantStreamKind>
  reasoningStartTimeRef: MutableRefObject<number | null>
  toolCallStartTimesRef: MutableRefObject<Record<string, number>>
  reasoningBlockCounterRef: MutableRefObject<number>
  contentBlockCounterRef: MutableRefObject<number>
  requestModeRef: MutableRefObject<RequestMode>
  requestKnowledgeBaseRef: MutableRefObject<KnowledgeBase | null>
  requestMcpConfigRef: MutableRefObject<Record<string, unknown> | null>
  retryActionsRef: MutableRefObject<Map<string, () => void | Promise<void>>>
  setMessagesAndRef: (
    updater: Message[] | ((prev: Message[]) => Message[])
  ) => void
  setThreadRunning: (threadId: string, running: boolean) => void
  getThreadRuntime: (threadId: string) => ThreadRuntime
  syncRuntimeToRefs: (runtime: ThreadRuntime) => void
  syncRuntimeToView: (runtime: ThreadRuntime) => void
  persistActiveRuntime: () => ThreadRuntime | null
  resetActiveChatView: (sessionId: string) => void
  scrollToBottom: () => void
  addMessage: (message: Message) => void
  ensureAssistantMessage: () => string
  updateAssistantMessage: (updater: (message: Message) => Message) => void
  applyAssistantError: (messageId: string | null, error: unknown) => void
  registerRetryAction: (
    messageId: string,
    action: () => void | Promise<void>
  ) => void
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  withAuthHeaders: (headers?: HeadersInit) => HeadersInit
  navigateTo: (
    viewMode: ViewMode,
    knowledgePage?: KnowledgePage,
    channelPage?: ChannelManagementPage,
    replace?: boolean
  ) => void
  knowledgeIndexNames: string[]
  primaryKnowledgeBase: KnowledgeBase | null
  mcpConfig: Record<string, unknown> | null
  mcpEnabled: boolean
  activeChatModeId: string
  setManagementError: (value: string) => void
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>
  loadHistorySessions: () => Promise<void>
}

export function useChatRuntime(deps: UseChatRuntimeDeps) {
  const {
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
  } = deps

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

  const refreshAssistantTokenUsage = useCallback(
    async (threadId: string, assistantMessageId: string) => {
      if (!threadId || !assistantMessageId) return
      try {
        const response = await requestJson<{ messages?: unknown }>(
          AGUI_THREAD_STATE_API_PATH(threadId)
        )
        const usage = getLatestAssistantTokenUsage(response.messages)
        if (!usage) return
        setMessagesAndRef((prev) =>
          prev.map((message) =>
            message.id === assistantMessageId
              ? { ...message, tokenUsage: usage }
              : message
          )
        )
      } catch {
        // Token 统计失败不能影响已经完成的回答。
      }
    },
    [requestJson, setMessagesAndRef]
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
      let finishedAssistantMessageId = ''

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
            finishedAssistantMessageId =
              currentAssistantMessageIdRef.current || ''
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

      if (completed && !stale && finishedAssistantMessageId) {
        await refreshAssistantTokenUsage(threadId, finishedAssistantMessageId)
      }

      return { interrupted, completed, stale }
    },
    [
      getThreadRuntime,
      handleAgUiEvent,
      isCurrentStream,
      refreshAssistantTokenUsage,
      setThreadRunning,
    ]
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

    const selectedAgentId = runtime.agentId ?? activeChatModeId
    const requestMode: RequestMode = selectedAgentId === KNOWLEDGE_AGENT_ID ? 'rag' : 'agent'
    if (
      availableAgents.length > 0 &&
      !availableAgents.some((agent) => agent.id === selectedAgentId)
    ) {
      setManagementError(`智能体 ${selectedAgentId} 当前不可用。`)
      return
    }
    const requestMcpConfig = requestMode === 'agent' && mcpEnabled ? mcpConfig : null
    if (requestMode === 'rag' && knowledgeIndexNames.length === 0) {
      setManagementError('启用知识库问答后，必须先选择至少一个知识库。')
      navigateTo('knowledge', 'libraries')
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
    requestKnowledgeBaseRef.current = primaryKnowledgeBase
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
    runtime.requestKnowledgeBase = primaryKnowledgeBase
    runtime.requestMcpConfig = requestMcpConfig

    abortControllerRef.current = new AbortController()
    runtime.abortController = abortControllerRef.current

    try {
      const state: Record<string, unknown> = {
        internet_search: internetSearch,
        deep_thinking: deepThinking,
      }
      if (knowledgeIndexNames.length > 0) {
        // 知识库模式由中间件自动检索，通用模式交给 retrieve_context 工具按需检索。
        state.index_names = knowledgeIndexNames
      }
      if (requestMcpConfig) {
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



  return {
    sendMessage,
    handleKeyDown,
    askRecommendedQuestion,
    abortRequest,
    handleInterruptAction,
    handleAskUserResponse,
    switchToThread,
  }
}
