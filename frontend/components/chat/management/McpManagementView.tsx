'use client'

import { useEffect, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { McpServerSummary, McpToolMetadata } from '../utils/types'
import { McpServerEditor, loadMcpTools, type McpRequest } from './McpServerEditor'


interface McpManagementViewProps {
  mcpEnabled: boolean
  mcpConfigDraft: string
  mcpConfigDirty: boolean
  mcpNotice: string
  mcpError: string
  draftError: string
  savedServerCount: number
  savedServerSummaries: McpServerSummary[]
  savedConfig: Record<string, unknown> | null
  requestJson: McpRequest
  onMcpConfigDraftChange: (value: string) => void
  onSaveMcpConfig: () => boolean
  onSaveMcpServer: (originalName: string | null, name: string, server: Record<string, unknown>) => boolean
  onFormatMcpConfig: () => void
  onToggleMcpEnabled: () => void
  onToggleMcpServer: (name: string) => void
  onLoadMcpExample: () => void
  onClearMcpConfig: () => void
}

export function McpManagementView({
  mcpEnabled,
  mcpConfigDraft,
  mcpConfigDirty,
  mcpNotice,
  mcpError,
  draftError,
  savedServerCount,
  savedServerSummaries,
  savedConfig,
  requestJson,
  onMcpConfigDraftChange,
  onSaveMcpConfig,
  onSaveMcpServer,
  onFormatMcpConfig,
  onToggleMcpEnabled,
  onToggleMcpServer,
  onLoadMcpExample,
  onClearMcpConfig,
}: McpManagementViewProps) {
  const [editorOpen, setEditorOpen] = useState(false)
  const [serverEditor, setServerEditor] = useState<{ name: string | null; config: Record<string, unknown> } | null>(null)
  const [expandedServer, setExpandedServer] = useState<string | null>(null)
  const [testSequence, setTestSequence] = useState(0)
  const [search, setSearch] = useState('')
  const savedServers = savedConfig?.mcpServers as Record<string, Record<string, unknown>> | undefined
  const visibleServers = savedServerSummaries.filter((server) =>
    `${server.name} ${server.transport}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase())
  )

  useEffect(() => {
    if (!editorOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setEditorOpen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [editorOpen])

  return (
    <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace}`}>
      <header className={styles.extensionHeading}>
        <div>
          <span className={styles.extensionEyebrow}>EXTENSIONS / MCP</span>
          <h2>MCP 服务</h2>
          <p>管理通用 Agent 可用的外部工具服务。</p>
        </div>
        <div className={styles.extensionHeadingActions}>
          <span className={styles.extensionCount}>{savedServerCount} 个已保存</span>
          <button className={styles.extensionSecondaryButton} onClick={() => setEditorOpen(true)}>批量配置</button>
          <button className={styles.extensionPrimaryButton} onClick={() => setServerEditor({ name: null, config: {} })}>
            <span aria-hidden="true">＋</span> 新增服务
          </button>
        </div>
      </header>

      {(mcpNotice || mcpError) && (
        <div role={mcpError ? 'alert' : 'status'} className={mcpError ? styles.managementError : styles.managementNotice}>
          {mcpError || mcpNotice}
        </div>
      )}

      <div className={styles.extensionSectionLabel}>运行设置</div>
      <div className={styles.extensionSettingRow}>
        <div className={styles.extensionSettingIcon} aria-hidden="true">M</div>
        <div className={styles.extensionSettingText}>
          <strong>在对话中使用 MCP</strong>
          <span>控制通用 Agent 是否使用 MCP。服务开关在下次发送消息时生效。</span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={mcpEnabled}
          aria-label="在对话中使用 MCP"
          className={`${styles.extensionSwitch} ${mcpEnabled ? styles.extensionSwitchOn : ''}`}
          onClick={onToggleMcpEnabled}
        >
          <span />
        </button>
      </div>

      <div className={styles.extensionSectionHeading}>
        <div>
          <div className={styles.extensionSectionLabel}>已配置的服务 <span>{savedServerCount}</span></div>
          <p>展开服务可查看工具清单和参数。</p>
        </div>
        <label className={styles.extensionSearch}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索服务" aria-label="搜索 MCP 服务" />
        </label>
      </div>

      <div className={styles.extensionList}>
        {visibleServers.length === 0 ? (
          <div className={styles.extensionEmpty}>
            <strong>{search ? '没有匹配的服务' : '还没有配置 MCP 服务'}</strong>
            <span>{search ? '试试服务名称或传输方式。' : '点击「新增服务」，填写连接配置。'}</span>
          </div>
        ) : visibleServers.map((server) => (
          <div className={styles.extensionListEntry} key={server.name}>
            <div className={`${styles.extensionListRow} ${styles.mcpServerRow}`}>
            <button type="button"
              className={styles.extensionSkillExpand}
              onClick={() => setExpandedServer(expandedServer === server.name ? null : server.name)}
              aria-expanded={expandedServer === server.name}
            >
              <span className={`${styles.extensionChevron} ${expandedServer === server.name ? styles.extensionChevronOpen : ''}`} aria-hidden="true">⌄</span>
              <span className={styles.extensionServerIcon} aria-hidden="true">{server.name.slice(0, 1).toUpperCase()}</span>
              <span className={styles.extensionRowMain}>
                <strong>{server.name}</strong>
                <small>{server.enabled ? (mcpEnabled ? '已启用' : '总开关已关闭') : '已停用'}</small>
              </span>
              <span className={styles.extensionTransport}>{server.transport}</span>
            </button>
            <div className={styles.mcpServerActions}>
            <button className={styles.extensionTextButton} type="button" aria-label={`测试连接 ${server.name}`} onClick={() => {
              setExpandedServer(server.name)
              setTestSequence((value) => value + 1)
            }}>测试连接</button>
            <button className={styles.extensionTextButton} type="button" aria-label={`编辑 ${server.name}`} onClick={() => {
              setServerEditor({ name: server.name, config: savedServers?.[server.name] ?? {} })
            }}>编辑</button>
            <button
              type="button"
              role="switch"
              aria-checked={server.enabled}
              aria-label={`启用 MCP 服务 ${server.name}`}
              className={`${styles.extensionSwitch} ${server.enabled ? styles.extensionSwitchOn : ''}`}
              onClick={() => onToggleMcpServer(server.name)}
            ><span /></button>
            </div>
            </div>
            {expandedServer === server.name && (
              <McpToolList
                key={testSequence}
                name={server.name}
                configText={JSON.stringify(savedServers?.[server.name], (key, value) => key === 'disabled' ? undefined : value)}
                requestJson={requestJson}
              />
            )}
          </div>
        ))}
      </div>

      {serverEditor && (
        <McpServerEditor
          originalName={serverEditor.name}
          initialConfig={serverEditor.config}
          saveError={mcpError}
          requestJson={requestJson}
          onClose={() => setServerEditor(null)}
          onSave={(name, config) => {
            const saved = onSaveMcpServer(serverEditor.name, name, config)
            if (saved) {
              if (expandedServer === serverEditor.name && serverEditor.name !== null) setExpandedServer(name)
              setServerEditor(null)
            }
          }}
        />
      )}

      {editorOpen && (
        <div className={styles.extensionDialogOverlay} onMouseDown={(event) => {
          if (event.target === event.currentTarget) setEditorOpen(false)
        }}>
          <section className={styles.extensionDialog} role="dialog" aria-modal="true" aria-labelledby="mcp-editor-title">
            <div className={styles.extensionDialogHeader}>
              <div>
                <span className={styles.extensionEyebrow}>MCP CONFIGURATION</span>
                <h3 id="mcp-editor-title">批量配置</h3>
              </div>
              <button className={styles.extensionIconButton} onClick={() => setEditorOpen(false)} aria-label="关闭配置编辑器" title="关闭">×</button>
            </div>
            <p className={styles.extensionDialogHint}>{mcpConfigDirty ? '有未保存的更改。' : '使用 mcpServers JSON 配置服务，配置保存在此浏览器中。'}</p>
            <textarea
              className={styles.extensionCodeEditor}
              value={mcpConfigDraft}
              onChange={(event) => onMcpConfigDraftChange(event.target.value)}
              placeholder='{"mcpServers":{"example":{"type":"streamable-http","url":"http://127.0.0.1:8000/mcp"}}}'
              spellCheck={false}
              aria-label="MCP JSON 配置"
              autoFocus
            />
            {(draftError || mcpError) && <div role="alert" className={styles.managementError}>{draftError || mcpError}</div>}
            <div className={styles.extensionDialogFooter}>
              <div className={styles.extensionDialogUtilities}>
                <button onClick={onLoadMcpExample}>填入示例</button>
                <button onClick={onFormatMcpConfig}>格式化</button>
                <button className={styles.extensionDeleteButton} onClick={onClearMcpConfig}>清空</button>
              </div>
              <div className={styles.extensionDialogActions}>
                <button className={styles.extensionSecondaryButton} onClick={() => setEditorOpen(false)}>取消</button>
                <button className={styles.extensionPrimaryButton} onClick={() => {
                  if (onSaveMcpConfig()) setEditorOpen(false)
                }} disabled={Boolean(draftError)}>保存配置</button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

/** 读取单个服务的工具清单。Args: name 为服务名，configText 为已保存连接配置，requestJson 为鉴权请求函数。 */
function McpToolList({ name, configText, requestJson }: { name: string; configText: string; requestJson: McpRequest }) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ config: string; attempt: number; tools?: McpToolMetadata[]; error?: string } | null>(null)
  const [openTool, setOpenTool] = useState<string | null>(null)
  const current = result?.config === configText && result.attempt === attempt ? result : null

  useEffect(() => {
    const controller = new AbortController()
    void loadMcpTools(requestJson, name, JSON.parse(configText), controller.signal).then((tools) => {
      if (!controller.signal.aborted) setResult({ config: configText, attempt, tools })
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setResult({
        config: configText,
        attempt,
        error: error instanceof Error ? error.message : '无法读取工具清单。',
      })
    })
    return () => controller.abort()
  }, [attempt, configText, name, requestJson])

  return (
    <section className={styles.mcpTools} aria-label={`${name} 的工具`}>
      <header>
        <strong>工具清单{current?.tools ? `（${current.tools.length}）` : ''}</strong>
        {current && <button className={styles.extensionTextButton} type="button" onClick={() => setAttempt(attempt + 1)}>{current.error ? '重试' : '刷新'}</button>}
      </header>
      {!current && <p role="status">正在连接并读取工具清单…</p>}
      {current?.error && <p role="alert">{current.error}</p>}
      {current?.tools && <p role="status">连接成功</p>}
      {current?.tools?.length === 0 && <p>此服务没有公布工具。</p>}
      {current?.tools?.map((tool) => (
        <div className={styles.mcpTool} key={tool.name}>
          <button type="button" aria-expanded={openTool === tool.name} onClick={() => setOpenTool(openTool === tool.name ? null : tool.name)}>
            <span className={`${styles.extensionChevron} ${openTool === tool.name ? styles.extensionChevronOpen : ''}`} aria-hidden="true">⌄</span>
            <code>{tool.name}</code>
          </button>
          {openTool === tool.name && (
            <div className={styles.mcpToolDetail}>
              <p>{tool.description || '此工具没有提供说明。'}</p>
              <strong>输入参数</strong>
              {Array.isArray(tool.input_schema.required) && tool.input_schema.required.length > 0 && (
                <p>必填参数：{tool.input_schema.required.join('、')}</p>
              )}
              <pre>{JSON.stringify(tool.input_schema, null, 2)}</pre>
            </div>
          )}
        </div>
      ))}
    </section>
  )
}
