'use client'

import { useCallback, useEffect, useState } from 'react'
import type { MutableRefObject } from 'react'

import {
  DEFAULT_CHANNEL_PAGE,
  DEFAULT_KNOWLEDGE_PAGE,
} from '../utils/constants'
import { getRouteHash, parseRouteHash } from '../utils'
import { resolveChannelEntryPage } from '../utils/channelManagement'
import type {
  ChannelManagementPage,
  KnowledgeBase,
  KnowledgePage,
  ViewMode,
} from '../utils/types'

/**
 * 管理页面视图、侧边栏状态与哈希路由同步。
 *
 * Args:
 *   selectedKnowledgeBaseRef: 当前选中的知识库引用，用于修正深层路由。
 */
export function usePageRouting(
  selectedKnowledgeBaseRef: MutableRefObject<KnowledgeBase | null>
) {
  const [viewMode, setViewMode] = useState<ViewMode>('chat')
  const [channelPage, setChannelPage] =
    useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
  const [lastChannelPage, setLastChannelPage] =
    useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
  const [channelNavExpanded, setChannelNavExpanded] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [knowledgePage, setKnowledgePage] =
    useState<KnowledgePage>(DEFAULT_KNOWLEDGE_PAGE)

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
        !selectedKnowledgeBaseRef.current
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
    [channelPage, selectedKnowledgeBaseRef]
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
        !selectedKnowledgeBaseRef.current
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
  }, [selectedKnowledgeBaseRef])

  const handleChannelsNavClick = useCallback(() => {
    if (viewMode !== 'channels') {
      const nextPage = resolveChannelEntryPage(undefined, lastChannelPage)
      navigateTo('channels', DEFAULT_KNOWLEDGE_PAGE, nextPage)
      return
    }

    setChannelNavExpanded((current) => !current)
  }, [lastChannelPage, navigateTo, viewMode])

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

  return {
    viewMode,
    setViewMode,
    channelPage,
    setChannelPage,
    lastChannelPage,
    channelNavExpanded,
    setChannelNavExpanded,
    sidebarCollapsed,
    setSidebarCollapsed,
    knowledgePage,
    setKnowledgePage,
    navigateTo,
    handleChannelsNavClick,
    toggleSidebar,
    navigateToKnowledgeView,
  }
}
