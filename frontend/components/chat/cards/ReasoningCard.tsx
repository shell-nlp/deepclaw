import styles from '../../ChatInterface.module.css'
import type { ReasoningBlock } from '../utils/types'
import { formatDuration } from '../utils'

interface ReasoningCardProps {
  block: ReasoningBlock
  duration?: number
}

/**
 * 默认折叠思考正文，并在标题上显示浏览器记录的耗时。
 *
 * Args:
 *   block: 思考分段。
 *   duration: 当前实时耗时，结束后使用分段保存值。
 */
export function ReasoningCard({ block, duration = block.duration }: ReasoningCardProps) {

  return (
    <details className={styles.reasoningContainer}>
      <summary className={styles.reasoningHeader}>
        <span>思考</span>
        {duration !== undefined && (
          <span className={styles.reasoningDuration}>{formatDuration(duration)}</span>
        )}
        <span className={styles.reasoningChevron} aria-hidden="true" />
      </summary>
      <div className={styles.reasoningContent}>{block.content}</div>
    </details>
  )
}
