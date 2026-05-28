'use client'

import styles from '../ChatInterface.module.css'
import type { McpServerSummary } from './types'

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
  return (
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>MCP Management</span>
          <h2>管理 Agent 可用的 MCP 工具配置</h2>
          <p>
            这里保存的是前端本地 MCP 配置。保存并启用后，前端会在通用 Agent
            请求里附带 `mcp_config`。推荐统一使用标准 `mcpServers` 配置；一个
            JSON 可以同时包含多个 MCP 服务，当前 RAG 请求不会使用该配置。
          </p>
        </div>
        <div className={styles.managementHeroActions}>
          <button className={styles.managementMinorButton} onClick={onLoadMcpExample}>
            填入示例
          </button>
          <button className={styles.managementMinorButton} onClick={onSaveMcpConfig}>
            保存配置
          </button>
          <button
            className={
              mcpEnabled ? styles.managementDangerButton : styles.managementButton
            }
            onClick={onToggleMcpEnabled}
          >
            {mcpEnabled ? '停用 MCP' : '启用 MCP'}
          </button>
        </div>
      </section>

      <div className={styles.managementNoticeRow}>
        {mcpNotice ? <div className={styles.managementNotice}>{mcpNotice}</div> : null}
        {mcpError ? <div className={styles.managementError}>{mcpError}</div> : null}
      </div>

      <div className={styles.managementSummaryGrid}>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>运行状态</span>
          <strong className={styles.managementSummaryValue}>
            {mcpEnabled ? '已启用' : '未启用'}
          </strong>
          <span className={styles.managementMeta}>仅对通用 Agent 请求生效</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>已保存服务数</span>
          <strong className={styles.managementSummaryValue}>{savedServerCount}</strong>
          <span className={styles.managementMeta}>保存后写入浏览器本地存储</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>草稿状态</span>
          <strong className={styles.managementSummaryValue}>
            {mcpConfigDirty ? '未保存' : '已同步'}
          </strong>
          <span className={styles.managementMeta}>
            {draftError ? '草稿存在校验问题' : '草稿格式可被后端接收'}
          </span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>加载策略</span>
          <strong className={styles.managementSummaryValue}>全部服务</strong>
          <span className={styles.managementMeta}>
            后端会按 `mcpServers` 下的所有服务逐个加载工具
          </span>
        </div>
      </div>

      <div className={styles.managementPageGrid}>
        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>MCP JSON 配置</h3>
            <span className={styles.managementMeta}>
              {mcpConfigDirty ? '有未保存变更' : '当前草稿已保存'}
            </span>
          </div>

          <div className={styles.managementMetaPanel}>
            <span>要求: 根节点必须包含 `mcpServers`</span>
            <span>要求: `mcpServers` 至少包含一个服务</span>
            <span>支持: 在 `mcpServers` 下同时配置多个命名服务</span>
            <span>推荐: 优先使用 `streamable-http`，本地进程使用 `stdio`</span>
            <span>兼容: 旧的 `mcpServer` / `sse` 配置仍可继续使用</span>
          </div>

          <textarea
            className={styles.managementTextarea}
            value={mcpConfigDraft}
            onChange={(event) => onMcpConfigDraftChange(event.target.value)}
            placeholder='请输入 MCP JSON 配置，例如 {"mcpServers":{"math":{"type":"streamable-http","url":"http://127.0.0.1:8000/mcp"},"local-file":{"type":"stdio","command":"python","args":["server.py"]}}}'
            spellCheck={false}
            rows={18}
          />

          {draftError ? (
            <div className={styles.managementError}>{draftError}</div>
          ) : (
            <div className={styles.managementHelperText}>
              保存时会自动格式化为标准 `mcpServers` JSON，并在启用后附加到
              Agent 请求体。旧的 `sse` 配置仍兼容，但新配置建议统一改成推荐写法。
            </div>
          )}

          <div className={styles.managementToolbar}>
            <button className={styles.managementButton} onClick={onSaveMcpConfig}>
              保存并格式化
            </button>
            <button className={styles.managementMinorButton} onClick={onFormatMcpConfig}>
              仅格式化
            </button>
            <button className={styles.managementMinorButton} onClick={onLoadMcpExample}>
              使用示例
            </button>
            <button
              className={styles.managementDangerMinorButton}
              onClick={onClearMcpConfig}
            >
              清空配置
            </button>
          </div>
        </section>

        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>服务预览</h3>
            <span className={styles.managementMeta}>
              {draftServerSummaries.length} 个服务
            </span>
          </div>

          <div className={styles.managementList}>
            {draftServerSummaries.length === 0 ? (
              <div className={styles.managementEmpty}>
                当前草稿还没有可预览的 MCP 服务
              </div>
            ) : (
              draftServerSummaries.map((server) => (
                <div key={server.name} className={styles.managementListItemStatic}>
                  <div className={styles.managementListHeader}>
                    <strong>{server.name}</strong>
                    <span>已配置</span>
                  </div>
                  <p className={styles.managementDescription}>{server.endpoint}</p>
                  <div className={styles.managementListMeta}>
                    <span>传输方式: {server.transport}</span>
                    <span>启用后会被后端读取并尝试加载工具</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
