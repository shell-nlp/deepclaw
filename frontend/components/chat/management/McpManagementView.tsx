'use client'

import { useEffect, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { McpServerSummary } from '../../chat-interface/types'

interface McpManagementViewProps {
  mcpEnabled: boolean
  mcpConfigDraft: string
  mcpConfigDirty: boolean
  mcpNotice: string
  mcpError: string
  draftError: string
  savedServerCount: number
  draftServerSummaries: McpServerSummary[]
  onMcpConfigDraftChange: (value: string) => void
  onSaveMcpConfig: () => void
  onFormatMcpConfig: () => void
  onToggleMcpEnabled: () => void
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
  draftServerSummaries,
  onMcpConfigDraftChange,
  onSaveMcpConfig,
  onFormatMcpConfig,
  onToggleMcpEnabled,
  onLoadMcpExample,
  onClearMcpConfig,
}: McpManagementViewProps) {
  const [editorOpen, setEditorOpen] = useState(false)
  const [expandedServer, setExpandedServer] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const visibleServers = draftServerSummaries.filter((server) =>
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
          <button className={styles.extensionPrimaryButton} onClick={() => setEditorOpen(true)}>
            <span aria-hidden="true">＋</span> 编辑配置
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
          <span>启用后仅加载已保存的服务；未配置时不加载 MCP 工具。知识库问答不使用此配置。</span>
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
          <div className={styles.extensionSectionLabel}>已配置的服务 <span>{draftServerSummaries.length}</span></div>
          <p>{mcpConfigDirty ? '当前显示未保存的草稿' : '服务配置保存在此浏览器中'}</p>
        </div>
        <label className={styles.extensionSearch}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索服务" aria-label="搜索 MCP 服务" />
        </label>
      </div>

      <div className={styles.extensionList}>
        {visibleServers.length === 0 ? (
          <div className={styles.extensionEmpty}>
            <strong>{search ? '没有匹配的服务' : draftError ? '配置需要修正' : '还没有配置 MCP 服务'}</strong>
            <span>{search ? '试试服务名称或传输方式。' : draftError || '打开配置编辑器，添加第一个服务。'}</span>
            {!search && <button className={styles.extensionTextButton} onClick={() => setEditorOpen(true)}>打开配置编辑器</button>}
          </div>
        ) : visibleServers.map((server) => (
          <div className={styles.extensionListEntry} key={server.name}>
            <button
              className={styles.extensionListRow}
              onClick={() => setExpandedServer(expandedServer === server.name ? null : server.name)}
              aria-expanded={expandedServer === server.name}
            >
              <span className={`${styles.extensionChevron} ${expandedServer === server.name ? styles.extensionChevronOpen : ''}`} aria-hidden="true">⌄</span>
              <span className={styles.extensionServerIcon} aria-hidden="true">{server.name.slice(0, 1).toUpperCase()}</span>
              <span className={styles.extensionRowMain}>
                <strong>{server.name}</strong>
                <small>已添加至当前配置</small>
              </span>
              <span className={styles.extensionTransport}>{server.transport}</span>
              <span className={styles.extensionRowEnd} aria-hidden="true">查看详情</span>
            </button>
            {expandedServer === server.name && (
              <div className={styles.extensionRowDetail}>
                <div><span>传输方式</span><strong>{server.transport}</strong></div>
                <div><span>配置详情</span><strong>在 JSON 编辑器中查看</strong></div>
                <button className={styles.extensionTextButton} onClick={() => setEditorOpen(true)}>编辑 JSON 配置</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {editorOpen && (
        <div className={styles.extensionDialogOverlay} onMouseDown={(event) => {
          if (event.target === event.currentTarget) setEditorOpen(false)
        }}>
          <section className={styles.extensionDialog} role="dialog" aria-modal="true" aria-labelledby="mcp-editor-title">
            <div className={styles.extensionDialogHeader}>
              <div>
                <span className={styles.extensionEyebrow}>MCP CONFIGURATION</span>
                <h3 id="mcp-editor-title">编辑服务配置</h3>
              </div>
              <button className={styles.extensionIconButton} onClick={() => setEditorOpen(false)} aria-label="关闭配置编辑器" title="关闭">×</button>
            </div>
            <p className={styles.extensionDialogHint}>使用标准 mcpServers JSON 配置多个服务。保存后仅在此浏览器生效。</p>
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
                  if (!draftError) onSaveMcpConfig()
                }} disabled={Boolean(draftError)}>保存配置</button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
