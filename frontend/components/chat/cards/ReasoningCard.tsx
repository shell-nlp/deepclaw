'use client'

import { useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { ReasoningBlock } from '../utils/types'
import { formatDuration } from '../utils'

interface ReasoningCardProps {
  block: ReasoningBlock
  duration?: number
}

/**
 * 展示思考正文及浏览器记录的耗时。
 *
 * Args:
 *   block: 思考分段。
 *   duration: 当前实时耗时，结束后使用分段保存值。
 */
export function ReasoningCard({ block, duration = block.duration }: ReasoningCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <section className={styles.reasoningContainer}>
      <button
        type="button"
        className={styles.reasoningHeader}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span>思考</span>
        {duration !== undefined && (
          <span className={styles.reasoningDuration}>{formatDuration(duration)}</span>
        )}
        <span className={styles.reasoningToggleIcon}>
          {expanded ? '−' : '+'}
        </span>
      </button>
      {expanded && (
        <div className={styles.reasoningContent}>{block.content}</div>
      )}
    </section>
  )
}
