'use client'

import { useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { ToolData } from '../utils/types'
import { formatDuration, getToolPreview } from '../utils'

interface ToolCardProps {
  toolData: ToolData
  duration?: number
}

export function ToolCard({ toolData, duration }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false)
  const toolName =
    toolData.toolCall?.tool_display_name || toolData.toolCall?.name || 'tool'

  const argsStr = toolData.toolCall?.args
    ? JSON.stringify(toolData.toolCall.args, null, 2)
    : ''

  const preview = getToolPreview(toolData)
  const hasResult = toolData.toolOutput?.some((output) => output.kind !== 'decision') ?? false
  const statusLabel = toolData.approvalStatus === 'pending' && !hasResult ? '等待审批'
    : toolData.approvalStatus === 'rejected' ? '已拒绝'
      : hasResult ? '工具执行完成'
        : toolData.approvalStatus === 'approved' || toolData.approvalStatus === 'edited'
          ? '已批准，等待工具结果' : '工具执行中'

  return (
    <div className={styles.toolCard}>
      <button
        type="button"
        className={styles.toolCardHeader}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span
          className={`${styles.toolStatus} ${
            hasResult ? styles.toolStatusSuccess : styles.toolStatusRunning
          }`}
          role="img"
          aria-label={statusLabel}
        />
        <span className={styles.toolName}>{toolName}</span>
        {toolData.approvalStatus && <span className={styles.toolPreview}>{statusLabel}</span>}
        {preview && <span className={styles.toolPreview}>{preview}</span>}
        {duration !== undefined && (
          <span className={styles.toolDuration}>{formatDuration(duration)}</span>
        )}
        <svg
          width="12"
          height="12"
          viewBox="0 0 10 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            flexShrink: 0,
            color: 'var(--text-muted)',
            transform: expanded ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.15s',
          }}
        >
          <polyline points="2 3.5 5 6.5 8 3.5" />
        </svg>
      </button>
      {expanded && (
        <div className={styles.toolCardDetails}>
          {toolData.toolCall && (
            <div className={styles.toolDetailSection}>
              <pre className={`${styles.toolDetailCode} ${styles.inputCode}`}>
                {argsStr}
              </pre>
            </div>
          )}
          {toolData.toolOutput?.map((output, index) => (
            <div key={index} className={styles.toolDetailSection}>
              <pre className={`${styles.toolDetailCode} ${styles.outputCode}`}>
                {output.content}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
