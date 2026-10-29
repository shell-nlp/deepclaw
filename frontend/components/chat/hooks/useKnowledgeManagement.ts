'use client'

import { ChangeEvent, MouseEvent, MutableRefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  DOCUMENT_CHUNK_PAGE_SIZE,
  DOCUMENT_PAGE_SIZE,
  GENERAL_AGENT_ID,
  KB_BULK_DELETE_API_PATH,
  KB_CREATE_API_PATH,
  KB_DELETE_API_PATH,
  KB_DETAIL_API_PATH,
  KB_DOCUMENT_BULK_DELETE_API_PATH,
  KB_DOCUMENT_CHUNK_UPDATE_API_PATH,
  KB_DOCUMENT_DELETE_API_PATH,
  KB_DOCUMENT_DETAIL_API_PATH,
  KB_DOCUMENT_LIST_API_PATH,
  KB_DOCUMENT_UPDATE_API_PATH,
  KB_DOCUMENT_UPLOAD_API_PATH,
  KB_DOCUMENT_UPLOAD_TASK_DELETE_API_PATH,
  KB_DOCUMENT_UPLOAD_TASK_RETRY_API_PATH,
  KB_DOCUMENT_UPLOAD_TASKS_API_PATH,
  KB_LIST_API_PATH,
  KB_UPDATE_API_PATH,
  KNOWLEDGE_AGENT_CAPABILITY,
  KNOWLEDGE_AGENT_ID,
  KNOWLEDGE_BASE_OPTION_PAGE_SIZE,
  KNOWLEDGE_BASE_PAGE_SIZE,
} from '../utils/constants'
import { getPageTotal, getRouteHash } from '../utils'
import type {
  AgentSummary,
  BulkDeleteDocumentResponse,
  BulkDeleteKnowledgeBaseResponse,
  ChannelManagementPage,
  ChatModeOption,
  KnowledgeBase,
  KnowledgeChunk,
  KnowledgeDocument,
  InterruptData,
  KnowledgeDocumentDetailResponse,
  KnowledgePage,
  KnowledgeUploadTask,
  PaginatedKnowledgeBaseResponse,
  PaginatedKnowledgeDocumentResponse,
  RequestMode,
  UploadResult,
  ViewMode,
} from '../utils/types'

type UseKnowledgeManagementOptions = {
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  currentUserId: string
  availableAgents: AgentSummary[]
  isKnowledgeMode: boolean
  setIsKnowledgeMode: (value: boolean) => void
  clearChat: () => void
  navigateTo: (viewMode: ViewMode, knowledgePage?: KnowledgePage, channelPage?: ChannelManagementPage, replace?: boolean) => void
  setViewMode: (mode: ViewMode) => void
  setKnowledgePage: (page: KnowledgePage) => void
  setManagementNotice: (notice: string) => void
  setManagementError: (error: string) => void
  knowledgePage: KnowledgePage
  channelPage: ChannelManagementPage
  requestKnowledgeBaseRef: MutableRefObject<KnowledgeBase | null>
  requestModeRef: MutableRefObject<RequestMode>
  setShowInterrupt: (value: boolean) => void
  setInterruptData: (value: InterruptData | null) => void
}

export function useKnowledgeManagement(options: UseKnowledgeManagementOptions) {
  const {
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
  } = options

  const [selectedKnowledgeBaseIds, setSelectedKnowledgeBaseIds] = useState<string[]>([])
  const [knowledgeBaseOptions, setKnowledgeBaseOptions] = useState<KnowledgeBase[]>([])
  const [knowledgePickerOpen, setKnowledgePickerOpen] = useState(false)
  const [loadingKnowledgeBaseOptions, setLoadingKnowledgeBaseOptions] = useState(false)

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
  const [uploadTasks, setUploadTasks] = useState<KnowledgeUploadTask[]>([])
  const uploadTaskStatusRef = useRef<Record<string, string>>({})
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

  const [loadingKnowledgeBases, setLoadingKnowledgeBases] = useState(false)
  const [loadingDocuments, setLoadingDocuments] = useState(false)
  const [savingKnowledgeBase, setSavingKnowledgeBase] = useState(false)
  const [uploadingDocuments, setUploadingDocuments] = useState(false)
  const [deletingBulk, setDeletingBulk] = useState(false)

  const uploadInputRef = useRef<HTMLInputElement>(null)

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

  const loadKnowledgeBaseOptions = useCallback(async () => {
    setLoadingKnowledgeBaseOptions(true)
    try {
      const result = await requestJson<PaginatedKnowledgeBaseResponse>(
        KB_LIST_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            search: '',
            page: 1,
            page_size: KNOWLEDGE_BASE_OPTION_PAGE_SIZE,
          }),
        }
      )
      setKnowledgeBaseOptions(result.items)
      return result.items
    } catch (error) {
      setManagementError(
        error instanceof Error ? error.message : '加载知识库列表失败。'
      )
      return [] as KnowledgeBase[]
    } finally {
      setLoadingKnowledgeBaseOptions(false)
    }
  }, [currentUserId, requestJson])

  const loadKnowledgeBaseDetail = useCallback(
    async (knowledgeBaseId: string, silent = false) => {
      if (!knowledgeBaseId) return
      if (!silent) setManagementError('')
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
        if (!silent) {
          setManagementError(error instanceof Error ? error.message : '加载知识库详情失败。')
        }
      }
    },
    [currentUserId, requestJson]
  )

  const loadDocuments = useCallback(
    async (
      knowledgeBaseId: string,
      page = documentPage,
      search = documentSearch,
      silent = false
    ) => {
      if (!knowledgeBaseId) {
        setDocuments([])
        setDocumentTotal(0)
        return
      }

      if (!silent) {
        setLoadingDocuments(true)
        setManagementError('')
      }
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
        if (!silent) {
          setManagementError(error instanceof Error ? error.message : '加载文档失败。')
          setDocuments([])
          setDocumentTotal(0)
        }
      } finally {
        if (!silent) setLoadingDocuments(false)
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


  useEffect(() => {
    void loadKnowledgeBases(knowledgeBasePage, knowledgeBaseSearch)
  }, [currentUserId, knowledgeBasePage, knowledgeBaseSearch, loadKnowledgeBases])

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
    if (!selectedKnowledgeBaseId || knowledgePage !== 'library-detail') return
    let active = true
    let refreshing = false
    const refresh = async () => {
      if (refreshing) return
      refreshing = true
      try {
        const tasks = await requestJson<KnowledgeUploadTask[]>(
          KB_DOCUMENT_UPLOAD_TASKS_API_PATH,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              user_id: currentUserId,
              knowledge_base_id: selectedKnowledgeBaseId,
            }),
          }
        )
        if (!active) return
        setUploadTasks(tasks)
        const changed = tasks.some((task) =>
          uploadTaskStatusRef.current[task.task_id] !== task.status
        )
        uploadTaskStatusRef.current = Object.fromEntries(
          tasks.map((task) => [task.task_id, task.status])
        )
        if (changed) {
          await loadDocuments(selectedKnowledgeBaseId, documentPage, documentSearch, true)
          await loadKnowledgeBaseDetail(selectedKnowledgeBaseId, true)
        }
      } catch {
        // 状态轮询失败不覆盖已有文档列表与管理提示。
      } finally {
        refreshing = false
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [selectedKnowledgeBaseId, knowledgePage, currentUserId, requestJson, loadDocuments, documentPage, documentSearch, loadKnowledgeBaseDetail])

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
      if (isKnowledgeMode && knowledgeBase.knowledge_base_id !== selectedKnowledgeBaseId) {
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
    [clearChat, selectedKnowledgeBaseId, isKnowledgeMode]
  )

  const applyKnowledgeSelection = useCallback(
    (ids: string[], options: KnowledgeBase[] = knowledgeBaseOptions) => {
      const uniqueIds = Array.from(new Set(ids))
      setSelectedKnowledgeBaseIds(uniqueIds)
      requestKnowledgeBaseRef.current =
        uniqueIds.length > 0
          ? options.find((item) => item.knowledge_base_id === uniqueIds[0]) ?? null
          : null
    },
    [knowledgeBaseOptions]
  )

  const handleKnowledgePickerOpenChange = useCallback(
    (open: boolean) => {
      setKnowledgePickerOpen(open)
      if (!open) return
      void (async () => {
        const options = knowledgeBaseOptions.length
          ? knowledgeBaseOptions
          : await loadKnowledgeBaseOptions()
        // 默认全选：首次打开或已清空选择时，把全部知识库选中。
        if (selectedKnowledgeBaseIds.length === 0 && options.length > 0) {
          applyKnowledgeSelection(
            options.map((item) => item.knowledge_base_id),
            options
          )
        }
      })()
    },
    [
      applyKnowledgeSelection,
      knowledgeBaseOptions,
      loadKnowledgeBaseOptions,
      selectedKnowledgeBaseIds,
    ]
  )

  const handleKnowledgeSelectionChange = useCallback(
    (ids: string[]) => applyKnowledgeSelection(ids),
    [applyKnowledgeSelection]
  )

  const chatModeOptions = useMemo<ChatModeOption[]>(() => {
    const knowledgeAgent = availableAgents.find((agent) =>
      agent.capabilities.includes(KNOWLEDGE_AGENT_CAPABILITY)
    )
    const generalAgent =
      availableAgents.find((agent) => agent.default) ??
      availableAgents.find(
        (agent) => !agent.capabilities.includes(KNOWLEDGE_AGENT_CAPABILITY)
      )
    return [
      {
        id: generalAgent?.id ?? GENERAL_AGENT_ID,
        label: generalAgent?.name ?? '通用智能体',
        description: generalAgent?.description,
        isKnowledge: false,
      },
      {
        id: knowledgeAgent?.id ?? KNOWLEDGE_AGENT_ID,
        label: knowledgeAgent?.name ?? '知识库问答',
        description: knowledgeAgent?.description,
        isKnowledge: true,
      },
    ]
  }, [availableAgents])

  const activeChatModeId =
    chatModeOptions.find((option) => option.isKnowledge === isKnowledgeMode)?.id ??
    chatModeOptions[0].id

  const handleChatModeChange = useCallback(
    (optionId: string) => {
      const option = chatModeOptions.find((item) => item.id === optionId)
      if (!option || option.isKnowledge === isKnowledgeMode) return

      clearChat()
      setShowInterrupt(false)
      setInterruptData(null)
      setKnowledgePickerOpen(false)
      requestModeRef.current = option.isKnowledge ? 'rag' : 'agent'
      setIsKnowledgeMode(option.isKnowledge)
      if (!option.isKnowledge) return

      // 切到知识库模式时默认全选知识库，避免必须先手动打开选择器才能提问。
      void (async () => {
        const options = knowledgeBaseOptions.length
          ? knowledgeBaseOptions
          : await loadKnowledgeBaseOptions()
        if (selectedKnowledgeBaseIds.length === 0 && options.length > 0) {
          applyKnowledgeSelection(
            options.map((item) => item.knowledge_base_id),
            options
          )
        }
      })()
    },
    [
      applyKnowledgeSelection,
      chatModeOptions,
      clearChat,
      knowledgeBaseOptions,
      loadKnowledgeBaseOptions,
      selectedKnowledgeBaseIds,
      isKnowledgeMode,
    ]
  )

  const knowledgeIndexNames = useMemo(() => {
    const names = selectedKnowledgeBaseIds
      .map(
        (id) =>
          knowledgeBaseOptions.find((item) => item.knowledge_base_id === id)
            ?.passage_index
      )
      .filter((name): name is string => Boolean(name))
    if (names.length > 0) return names
    return selectedKnowledgeBase ? [selectedKnowledgeBase.passage_index] : []
  }, [knowledgeBaseOptions, selectedKnowledgeBase, selectedKnowledgeBaseIds])

  const primaryKnowledgeBase = useMemo(
    () =>
      knowledgeBaseOptions.find(
        (item) => item.knowledge_base_id === selectedKnowledgeBaseIds[0]
      ) ?? selectedKnowledgeBase,
    [knowledgeBaseOptions, selectedKnowledgeBase, selectedKnowledgeBaseIds]
  )


  const openKnowledgeBaseLibrary = (knowledgeBase: KnowledgeBase) => {
    selectKnowledgeBase(knowledgeBase)
    setViewMode('knowledge')
    setKnowledgePage('library-detail')
    if (typeof window !== 'undefined') {
      window.history.pushState(null, '', getRouteHash('knowledge', 'library-detail', channelPage))
    }
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
      setUploadTasks((previous) => [
        ...result.tasks,
        ...previous.filter((task) => !result.tasks.some((item) => item.task_id === task.task_id)),
      ])
      if (result.tasks.length) {
        setManagementNotice(`已提交 ${result.tasks.length} 个文件，后台处理中。`)
      }
      if (result.errors.length) {
        setManagementError(result.errors.map((item) => `${item.file_name}: ${item.error}`).join('\n'))
      }
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '上传文件失败。')
    } finally {
      setUploadingDocuments(false)
      if (uploadInputRef.current) uploadInputRef.current.value = ''
    }
  }

  const retryUploadTask = async (task: KnowledgeUploadTask) => {
    if (!selectedKnowledgeBase) return
    setManagementError('')
    setManagementNotice('')
    try {
      const updated = await requestJson<KnowledgeUploadTask>(
        KB_DOCUMENT_UPLOAD_TASK_RETRY_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
            task_id: task.task_id,
          }),
        }
      )
      setUploadTasks((previous) =>
        previous.map((item) => (item.task_id === updated.task_id ? updated : item))
      )
      setManagementNotice(`已重新提交 ${updated.file_name}，后台处理中。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '重试上传任务失败。')
    }
  }

  const deleteUploadTask = async (task: KnowledgeUploadTask) => {
    if (!selectedKnowledgeBase) return
    if (!window.confirm(`确认删除失败的上传记录 "${task.file_name}" 吗？`)) return
    setManagementError('')
    setManagementNotice('')
    try {
      await requestJson<{ task_id: string; deleted: boolean }>(
        KB_DOCUMENT_UPLOAD_TASK_DELETE_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: currentUserId,
            knowledge_base_id: selectedKnowledgeBase.knowledge_base_id,
            task_id: task.task_id,
          }),
        }
      )
      setUploadTasks((previous) => previous.filter((item) => item.task_id !== task.task_id))
      setManagementNotice(`已删除上传记录 ${task.file_name}。`)
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '删除上传记录失败。')
    }
  }

  const updateDocumentChunk = async (
    chunk: KnowledgeChunk,
    changes: { content?: string; state?: boolean }
  ) => {
    if (!selectedDocumentDetail) return
    const knowledgeBaseId = selectedDocumentDetail.knowledge_base.knowledge_base_id
    const documentId = selectedDocumentDetail.document.document_id
    setManagementError('')
    setManagementNotice('')
    try {
      await requestJson<KnowledgeChunk>(KB_DOCUMENT_CHUNK_UPDATE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          knowledge_base_id: knowledgeBaseId,
          document_id: documentId,
          chunk_id: chunk.chunk_id,
          ...(changes.content === undefined ? {} : { content: changes.content }),
          ...(changes.state === undefined ? {} : { state: changes.state }),
        }),
      })
      await loadDocumentDetail(knowledgeBaseId, documentId, documentChunkPage)
      setManagementNotice(
        changes.state === undefined
          ? '切片内容已更新。'
          : changes.state
            ? '已启用该切片。'
            : '已停用该切片。'
      )
    } catch (error) {
      setManagementError(error instanceof Error ? error.message : '更新切片失败。')
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


  const resetKnowledgeState = useCallback(() => {
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
  }, [])

  return {
    selectedKnowledgeBaseIds,
    setSelectedKnowledgeBaseIds,
    knowledgeBaseOptions,
    setKnowledgeBaseOptions,
    knowledgePickerOpen,
    setKnowledgePickerOpen,
    loadingKnowledgeBaseOptions,
    setLoadingKnowledgeBaseOptions,
    knowledgeBases,
    setKnowledgeBases,
    knowledgeBaseTotal,
    setKnowledgeBaseTotal,
    knowledgeBasePage,
    setKnowledgeBasePage,
    knowledgeBaseSearchInput,
    setKnowledgeBaseSearchInput,
    knowledgeBaseSearch,
    setKnowledgeBaseSearch,
    selectedKnowledgeBaseId,
    setSelectedKnowledgeBaseId,
    selectedKnowledgeBase,
    setSelectedKnowledgeBase,
    checkedKnowledgeBaseIds,
    setCheckedKnowledgeBaseIds,
    documents,
    setDocuments,
    uploadTasks,
    setUploadTasks,
    uploadTaskStatusRef,
    documentTotal,
    setDocumentTotal,
    documentPage,
    setDocumentPage,
    documentSearchInput,
    setDocumentSearchInput,
    documentSearch,
    setDocumentSearch,
    checkedDocumentIds,
    setCheckedDocumentIds,
    selectedDocumentId,
    setSelectedDocumentId,
    selectedDocumentDetail,
    setSelectedDocumentDetail,
    documentChunkPage,
    setDocumentChunkPage,
    loadingDocumentDetail,
    setLoadingDocumentDetail,
    knowledgeBaseName,
    setKnowledgeBaseName,
    knowledgeBaseDescription,
    setKnowledgeBaseDescription,
    showCreateKnowledgeBaseModal,
    setShowCreateKnowledgeBaseModal,
    loadingKnowledgeBases,
    setLoadingKnowledgeBases,
    loadingDocuments,
    setLoadingDocuments,
    savingKnowledgeBase,
    setSavingKnowledgeBase,
    uploadingDocuments,
    setUploadingDocuments,
    deletingBulk,
    setDeletingBulk,
    uploadInputRef,
    loadKnowledgeBases,
    loadKnowledgeBaseOptions,
    loadKnowledgeBaseDetail,
    loadDocuments,
    loadDocumentDetail,
    selectKnowledgeBase,
    applyKnowledgeSelection,
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
    resetKnowledgeState,
  }
}
