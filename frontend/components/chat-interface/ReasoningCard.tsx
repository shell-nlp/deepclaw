'use client'

import { useState } from 'react'

import styles from '../ChatInterface.module.css'
import type { ReasoningBlock } from './types'
import { formatDuration } from './utils'

interface ReasoningCardProps {
  block: ReasoningBlock
}

export function ReasoningCard({ block }: ReasoningCardProps) {
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
        {block.duration !== undefined && (
          <span className={styles.reasoningDuration}>{formatDuration(block.duration)}</span>
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
