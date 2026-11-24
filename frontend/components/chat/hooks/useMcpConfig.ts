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
  const activeServerCount = savedMcpParseResult.serverSummaries.filter((server) => server.enabled).length

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
      try {
        localStorage.removeItem('rag_mcp_config')
      } catch {
        setMcpError('无法写入浏览器存储，请检查浏览器设置。')
        return false
      }
      setSavedMcpConfigText('')
      setMcpConfigDraft('')
      setMcpConfig(null)
      setMcpNotice('MCP 配置已清空。')
      setMcpError('')
      return true
    }

    const parsed = parseMcpConfig(trimmed)
    if (!parsed.config || parsed.error) {
      setMcpNotice('')
      setMcpError(parsed.error || 'MCP 配置无效，无法保存。')
      return false
    }

    const formatted = JSON.stringify(parsed.config, null, 2)
    try {
      localStorage.setItem('rag_mcp_config', formatted)
    } catch {
      setMcpError('无法写入浏览器存储，请检查浏览器设置。')
      return false
    }

    setSavedMcpConfigText(formatted)
    setMcpConfigDraft(formatted)
    setMcpConfig(parsed.config)
    setMcpNotice(`已保存 ${parsed.serverSummaries.length} 个 MCP 服务配置。`)
    setMcpError('')
    return true
  }

  /** 更新已保存的服务开关。Args: name 为服务名称。 */
  const toggleMcpServer = (name: string) => {
    const config = savedMcpParseResult.config
    const servers = config?.mcpServers as Record<string, Record<string, unknown>> | undefined
    if (!servers || !Object.prototype.hasOwnProperty.call(servers, name)) return
    const server = { ...servers[name] }
    if (server.disabled === true) delete server.disabled
    else server.disabled = true
    const next = { ...config, mcpServers: { ...servers, [name]: server } }
    const formatted = JSON.stringify(next, null, 2)
    try {
      localStorage.setItem('rag_mcp_config', formatted)
    } catch {
      setMcpError('无法写入浏览器存储，请检查浏览器设置。')
      return
    }
    setSavedMcpConfigText(formatted)
    if (!mcpConfigDirty) setMcpConfigDraft(formatted)
    setMcpConfig(next)
    setMcpError('')
    setMcpNotice(server.disabled ? '已停用服务，下次发送消息时生效。' : '已启用服务，下次发送消息时生效。')
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
    setMcpNotice('MCP 已启用，下次发送消息时生效。')
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
      : `已启用 ${activeServerCount} 个服务`
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
    toggleMcpServer,
    loadMcpExample,
    clearMcpConfig,
    mcpStatusLabel,
  }
}
