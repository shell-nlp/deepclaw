'use client'

import { useCallback, useEffect, useState } from 'react'
import type { MouseEvent, MutableRefObject } from 'react'

import {
  AGUI_THREADS_API_PATH,
  AGUI_THREAD_DELETE_API_PATH,
} from '../utils/constants'
import { generateSessionId } from '../utils'
import type { ThreadRuntime } from '../utils/chatRuntime'
import type {
  ChatHistorySession,
  KnowledgePage,
  ThreadListResponse,
  ViewMode,
} from '../utils/types'

type UseHistorySessionsOptions = {
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  sessionId: string
  runningThreadIds: string[]
  switchToThreadRef: MutableRefObject<(threadId: string) => Promise<void>>
  navigateTo: (viewMode: ViewMode, knowledgePage?: KnowledgePage) => void
  scrollToBottom: () => void
  threadRuntimesRef: MutableRefObject<Map<string, ThreadRuntime>>
  setThreadRunning: (threadId: string, running: boolean) => void
  streamGenerationRef: MutableRefObject<number>
  abortControllerRef: MutableRefObject<AbortController | null>
  resetActiveChatView: (sessionId: string) => void
  getThreadRuntime: (threadId: string) => ThreadRuntime
}

/**
 * 管理聊天历史会话的加载、切换与删除。
 *
 * Args:
 *   options: 请求、会话与运行时相关依赖。
 */
export function useHistorySessions({
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
}: UseHistorySessionsOptions) {
  const [historySessions, setHistorySessions] = useState<ChatHistorySession[]>([])
  const [historyExpanded, setHistoryExpanded] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoadingSessionId, setHistoryLoadingSessionId] = useState<string | null>(null)
  const [historyError, setHistoryError] = useState('')

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
    [navigateTo, scrollToBottom, sessionId, switchToThreadRef]
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
      abortControllerRef,
      getThreadRuntime,
      requestJson,
      resetActiveChatView,
      runningThreadIds,
      sessionId,
      setThreadRunning,
      streamGenerationRef,
      threadRuntimesRef,
    ]
  )

  useEffect(() => {
    void loadHistorySessions()
  }, [loadHistorySessions])

  return {
    historySessions,
    setHistorySessions,
    historyExpanded,
    setHistoryExpanded,
    historyLoading,
    historyLoadingSessionId,
    historyError,
    loadHistorySessions,
    openHistorySession,
    deleteHistorySession,
  }
}
