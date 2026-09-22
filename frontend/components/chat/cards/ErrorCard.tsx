import styles from '../../ChatInterface.module.css'
import type { ChatError } from '../../chat-interface/types'

interface ErrorCardProps {
  error: ChatError
  onRetry?: () => void | Promise<void>
}

/**
 * 渲染 assistant 消息内的统一错误卡片。
 *
 * Args:
 *   error: 前端归一化后的错误信息。
 *   onRetry: 可选的错误重试回调。
 */
export function ErrorCard({ error, onRetry }: ErrorCardProps) {
  const detail =
    error.detail && error.detail !== error.message ? error.detail : undefined

  return (
    <div className={styles.errorCard} role="alert">
      <span className={styles.errorCardIcon} aria-hidden="true">
        !
      </span>
      <div className={styles.errorCardBody}>
        <div className={styles.errorCardTitle}>{error.title}</div>
        <div className={styles.errorCardMessage}>{error.message}</div>
        {detail ? (
          <pre className={styles.errorCardDetail}>{detail}</pre>
        ) : null}
        {error.status ? (
          <div className={styles.errorCardMeta}>HTTP {error.status}</div>
        ) : null}
      </div>
      {error.retryable && onRetry ? (
        <button
          type="button"
          className={styles.errorCardRetry}
          onClick={() => void onRetry()}
        >
          重试
        </button>
      ) : null}
    </div>
  )
}
