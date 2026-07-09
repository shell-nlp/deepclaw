'use client'

import { useState } from 'react'

import styles from '../ChatInterface.module.css'
import type { ReasoningBlock } from './types'
import { formatDuration } from './utils'

interface ReasoningCardProps {
  block: ReasoningBlock
  duration?: number
}

export function ReasoningCard({ block, duration }: ReasoningCardProps) {
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
