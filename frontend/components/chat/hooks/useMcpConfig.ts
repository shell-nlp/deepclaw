'use client'

import { useEffect, useState } from 'react'

import { DEFAULT_MCP_CONFIG_TEMPLATE } from '../utils/constants'
import { parseMcpConfig } from '../utils'
import type { ViewMode } from '../utils/types'

/**
 * 管理 MCP 配置草稿、启用状态与本地持久化。
 *
 * Args:
 *   viewMode: 当前页面视图，用于离开 MCP 页时清理提示。
 *   isKnowledgeMode: 当前是否处于知识库问答模式。
 */
export function useMcpConfig(viewMode: ViewMode, isKnowledgeMode: boolean) {
  const [mcpConfigDraft, setMcpConfigDraft] = useState('')
  const [savedMcpConfigText, setSavedMcpConfigText] = useState('')
  const [mcpConfig, setMcpConfig] = useState<Record<string, unknown> | null>(null)
  const [mcpEnabled, setMcpEnabled] = useState(false)
  const [mcpNotice, setMcpNotice] = useState('')
  const [mcpError, setMcpError] = useState('')

  useEffect(() => {
    if (!mcpNotice) return
    const timeout = window.setTimeout(() => setMcpNotice(''), 4000)
    return () => window.clearTimeout(timeout)
  }, [mcpNotice])

  useEffect(() => {
    if (viewMode !== 'mcp') setMcpNotice('')
  }, [viewMode])

  const mcpDraftParseResult = parseMcpConfig(mcpConfigDraft)
  const savedMcpParseResult = parseMcpConfig(savedMcpConfigText)
  const mcpConfigDirty = mcpConfigDraft !== savedMcpConfigText

  const initializeMcpConfig = (raw: string, enabled: boolean) => {
    const parsed = parseMcpConfig(raw)
    setMcpConfigDraft(raw)
    setSavedMcpConfigText(raw)
    setMcpConfig(parsed.config)
    setMcpEnabled(enabled)
    if (raw && parsed.error) {
      setMcpError(`本地保存的 MCP 配置无效：${parsed.error}`)
    }
  }

  const saveMcpConfig = () => {
    const trimmed = mcpConfigDraft.trim()

    if (!trimmed) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('rag_mcp_config')
      }
      setSavedMcpConfigText('')
      setMcpConfigDraft('')
      setMcpConfig(null)
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

    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_mcp_enabled', 'true')
    }
    setMcpEnabled(true)
    setMcpNotice(mcpConfig ? 'MCP 已启用，通用 Agent 将使用已保存的配置。' : 'MCP 已启用；当前没有配置服务，聊天不会加载 MCP 工具。')
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

  const mcpStatusLabel = mcpEnabled
    ? isKnowledgeMode
      ? '已启用，但当前 RAG 不使用'
      : savedMcpParseResult.serverSummaries.length > 0
        ? `已启用 ${savedMcpParseResult.serverSummaries.length} 个服务`
        : '已启用'
    : savedMcpParseResult.serverSummaries.length > 0
      ? `已配置 ${savedMcpParseResult.serverSummaries.length} 个服务`
      : '未配置'

  return {
    mcpConfigDraft,
    setMcpConfigDraft,
    savedMcpConfigText,
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
  }
}
