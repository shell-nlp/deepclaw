'use client'

import { useState } from 'react'

import styles from '../ChatInterface.module.css'
import type { ToolData } from './types'
import { formatDuration, getToolPreview } from './utils'

interface ToolCardProps {
  toolData: ToolData
  duration?: number
}

export function ToolCard({ toolData, duration }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false)
  const toolName = toolData.toolCall?.name || 'tool'

  const argsStr = toolData.toolCall?.args
    ? JSON.stringify(toolData.toolCall.args, null, 2)
    : ''

  const preview = getToolPreview(toolData)

  return (
    <div className={`${styles.toolCard} ${styles.success}`}>
      <button
        type="button"
        className={styles.toolCardHeader}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className={styles.toolName}>{toolName}</span>
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
