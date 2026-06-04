'use client'

import { marked } from 'marked'

import {
  DEFAULT_BACKEND_URL,
  DEFAULT_KNOWLEDGE_PAGE,
} from './constants'
import type { KnowledgePage, McpServerSummary, ViewMode } from './types'

export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_BASE_URL
  if (envUrl) return envUrl.replace(/\/$/, '')

  if (typeof window === 'undefined') return ''

  const { hostname, origin } = window.location
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return DEFAULT_BACKEND_URL
  }

  return origin
}

export function getApiUrl(path: string): string {
  return `${getApiBaseUrl()}${path}`
}

export function normalizeKnowledgePage(value?: string): KnowledgePage {
  switch (value) {
    case 'library-detail':
    case 'document-detail':
    case 'users':
      return value
    default:
      return 'libraries'
  }
}

export function getRouteHash(
  viewMode: ViewMode,
  knowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE
): string {
  if (viewMode === 'chat') return '#/chat'
  if (viewMode === 'mcp') return '#/mcp'
  if (viewMode === 'skills') return '#/skills'
  if (viewMode === 'channels') return '#/channels'
  return `#/knowledge/${knowledgePage}`
}

export function parseRouteHash(hash: string): {
  viewMode: ViewMode
  knowledgePage: KnowledgePage
} {
  const normalized = hash.replace(/^#/, '').replace(/^\/+/, '')
  const parts = normalized.split('/').filter(Boolean)

  if (parts[0] === 'mcp') {
    return {
      viewMode: 'mcp',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
    }
  }

  if (parts[0] === 'skills') {
    return {
      viewMode: 'skills',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
    }
  }

  if (parts[0] === 'channels') {
    return {
      viewMode: 'channels',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
    }
  }

  if (parts[0] === 'knowledge') {
    return {
      viewMode: 'knowledge',
      knowledgePage: normalizeKnowledgePage(parts[1]),
    }
  }

  return {
    viewMode: 'chat',
    knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
  }
}

export function generateSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

export function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
}

export function getPageTotal(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize))
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const payload = await response.json()
      if (payload?.detail) {
        message = String(payload.detail)
      }
    } catch {
      // ignore parse error
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function getToolIcon(toolName: string): string {
  const iconMap: Record<string, string> = {
    search: 'S',
    calculator: 'M',
    calc: 'M',
    math: 'M',
    weather: 'W',
    time: 'T',
    date: 'D',
    file: 'F',
    read: 'R',
    write: 'W',
    edit: 'E',
    api: 'A',
    http: 'A',
    request: 'A',
    fetch: 'A',
    python: 'P',
    code: 'C',
    exec: 'C',
    run: 'R',
    bash: 'B',
    git: 'G',
    translate: 'TR',
    analyze: 'AN',
    browser: 'BR',
  }
  const lower = toolName.toLowerCase()
  for (const [key, icon] of Object.entries(iconMap)) {
    if (lower.includes(key)) return icon
  }
  return 'TL'
}

export function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function parseMarkdown(text: string): string {
  try {
    return marked.parse(text, { async: false }) as string
  } catch {
    return escapeHtml(text)
  }
}

export function stringifyToolContent(content: unknown): string {
  if (typeof content === 'string') return content
  if (content == null) return ''
  try {
    return JSON.stringify(content, null, 2)
  } catch {
    return String(content)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizeMcpTransport(value: string): string {
  const normalized = value.trim().toLowerCase()
  if (
    normalized === 'streamablehttp' ||
    normalized === 'streamable-http' ||
    normalized === 'streamable_http' ||
    normalized === 'http'
  ) {
    return 'streamable-http'
  }
  if (normalized === 'sse') return 'sse'
  if (normalized === 'stdio') return 'stdio'
  return value
}

function normalizeMcpServerConfig(
  serverConfig: Record<string, unknown>
): Record<string, unknown> {
  const normalizedConfig: Record<string, unknown> = { ...serverConfig }
  const transport =
    typeof serverConfig.type === 'string'
      ? serverConfig.type
      : typeof serverConfig.transport === 'string'
        ? serverConfig.transport
        : null

  if (transport) {
    normalizedConfig.type = normalizeMcpTransport(transport)
  }

  delete normalizedConfig.transport
  return normalizedConfig
}

function getMcpServerRoot(
  parsed: Record<string, unknown>
): { serverRoot: Record<string, unknown> | null; error: string } {
  if (isRecord(parsed.mcpServers)) {
    return {
      serverRoot: parsed.mcpServers,
      error: '',
    }
  }

  if (isRecord(parsed.mcpServer)) {
    return {
      serverRoot: parsed.mcpServer,
      error: '',
    }
  }

  if (typeof parsed.mcpServer === 'string') {
    try {
      const innerParsed = JSON.parse(parsed.mcpServer)
      if (!isRecord(innerParsed)) {
        return {
          serverRoot: null,
          error: '`mcpServer` 解析后必须是 JSON 对象。',
        }
      }
      return {
        serverRoot: innerParsed,
        error: '',
      }
    } catch {
      return {
        serverRoot: null,
        error: '`mcpServer` 不是合法 JSON 字符串，请先修正后再保存。',
      }
    }
  }

  return {
    serverRoot: null,
    error: 'MCP 配置必须包含 `mcpServers` 对象，或兼容的 `mcpServer` 配置。',
  }
}

export function parseMcpConfig(raw: string): {
  config: Record<string, unknown> | null
  serverSummaries: McpServerSummary[]
  error: string
} {
  const trimmed = raw.trim()
  if (!trimmed) {
    return {
      config: null,
      serverSummaries: [],
      error: '',
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return {
      config: null,
      serverSummaries: [],
      error: 'MCP 配置不是合法 JSON，请先修正后再保存。',
    }
  }

  if (!isRecord(parsed)) {
    return {
      config: null,
      serverSummaries: [],
      error: 'MCP 配置根节点必须是 JSON 对象。',
    }
  }

  const { serverRoot, error } = getMcpServerRoot(parsed)
  if (!serverRoot) {
    return {
      config: null,
      serverSummaries: [],
      error,
    }
  }

  const serverEntries = Object.entries(serverRoot).filter(([, value]) => isRecord(value))
  if (serverEntries.length === 0) {
    return {
      config: null,
      serverSummaries: [],
      error: '`mcpServers` 或 `mcpServer` 至少需要配置一个服务。',
    }
  }

  const normalizedServerEntries = serverEntries.map(([name, value]) => [
    name,
    normalizeMcpServerConfig(value as Record<string, unknown>),
  ] as const)

  const serverSummaries = normalizedServerEntries.map(([name, serverConfig]) => {
    const transport =
      typeof serverConfig.type === 'string'
        ? serverConfig.type
        : typeof serverConfig.url === 'string'
          ? 'streamable-http'
          : typeof serverConfig.command === 'string'
            ? 'stdio'
            : 'unknown'

    let endpoint = '未填写连接信息'
    if (typeof serverConfig.url === 'string' && serverConfig.url.trim()) {
      endpoint = serverConfig.url
    } else if (
      typeof serverConfig.command === 'string' &&
      serverConfig.command.trim()
    ) {
      const args = Array.isArray(serverConfig.args)
        ? serverConfig.args.map((item: unknown) => String(item)).join(' ')
        : ''
      endpoint = `${serverConfig.command}${args ? ` ${args}` : ''}`
    }

    return {
      name,
      transport,
      endpoint,
    }
  })

  return {
    config: {
      ...parsed,
      mcpServers: Object.fromEntries(normalizedServerEntries),
    },
    serverSummaries,
    error: '',
  }
}
