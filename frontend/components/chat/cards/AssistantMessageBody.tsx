import styles from '../../ChatInterface.module.css'
import type { Message } from '../../chat-interface/types'
import { normalizeChartMarkdown, parseMarkdown } from '../../chat-interface/utils'
import { getAssistantMessageItems } from '../utils/assistantMessage'
import { ErrorCard } from './ErrorCard'
import { ProcessSummary } from './ProcessSummary'

interface AssistantMessageBodyProps {
  msg: Message
  toolCallDurations?: Record<string, number>
  isProcessing: boolean
  onRecommendedQuestion: (question: string) => void | Promise<void>
  onRetryMessage: (messageId: string) => void | Promise<void>
}

/**
 * 渲染单条 assistant 消息的推理、工具、正文和错误区域。
 *
 * Args:
 *   msg: 当前 assistant 消息。
 *   toolCallDurations: 基于浏览器时间计算的工具调用耗时。
 *   isProcessing: 当前消息是否仍在处理中。
 *   onRecommendedQuestion: 推荐问题点击回调。
 *   onRetryMessage: 错误重试回调。
 */
export function AssistantMessageBody({
  msg,
  toolCallDurations,
  isProcessing,
  onRecommendedQuestion,
  onRetryMessage,
}: AssistantMessageBodyProps) {
  const reasoningBlocks = msg.reasoningBlocks?.length
    ? msg.reasoningBlocks
    : msg.reasoningContent
      ? [{ id: `${msg.id}_reasoning_legacy`, content: msg.reasoningContent }]
      : []
  const contentBlocks = msg.contentBlocks?.length
    ? msg.contentBlocks
    : msg.content
      ? [{ id: `${msg.id}_content_legacy`, content: msg.content }]
      : []
  const assistantItems = getAssistantMessageItems(msg)
  const firstToolIndex = assistantItems.findIndex(
    (item) => item.type === 'tool'
  )
  const visibleContentIds = new Set(
    (firstToolIndex >= 0
      ? assistantItems.slice(firstToolIndex + 1)
      : assistantItems
    )
      .filter((item) => item.type === 'content')
      .map((item) => item.contentBlockId)
  )
  const visibleContentBlocks = contentBlocks.filter((block) =>
    visibleContentIds.has(block.id)
  )

  return (
    <>
      <ProcessSummary
        msg={msg}
        reasoningBlocks={reasoningBlocks}
        toolCallDurations={toolCallDurations}
        isProcessing={isProcessing}
      />
      {visibleContentBlocks.map((block) => (
        <div
          key={block.id}
          className={styles.messageContent}
          dangerouslySetInnerHTML={{
            __html: parseMarkdown(normalizeChartMarkdown(block.content, msg.toolData)),
          }}
        />
      ))}
      {!isProcessing && msg.tokenUsage ? (
        <div className={styles.tokenUsage}>
          <span className={styles.tokenUsageLabel}>Token 用量</span>
          <span>
            输入{' '}
            <strong>{msg.tokenUsage.inputTokens.toLocaleString('zh-CN')}</strong>
          </span>
          <span className={styles.tokenUsageDivider}>·</span>
          <span>
            输出{' '}
            <strong>{msg.tokenUsage.outputTokens.toLocaleString('zh-CN')}</strong>
          </span>
          <span className={styles.tokenUsageDivider}>·</span>
          <span>
            总计{' '}
            <strong>{msg.tokenUsage.totalTokens.toLocaleString('zh-CN')}</strong>
          </span>
        </div>
      ) : null}
      {msg.recommendedQuestions?.length ? (
        <div className={styles.recommendedQuestions}>
          <span className={styles.recommendedQuestionsTitle}>你可能还想问：</span>
          <div className={styles.recommendedQuestionsList}>
            {msg.recommendedQuestions.map((question) => (
              <button
                key={question}
                className={styles.recommendedQuestionButton}
                onClick={() => void onRecommendedQuestion(question)}
              >
                <span>{question}</span>
                <span aria-hidden="true">→</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {msg.error ? (
        <ErrorCard
          error={msg.error}
          onRetry={() => onRetryMessage(msg.id)}
        />
      ) : null}
    </>
  )
}
