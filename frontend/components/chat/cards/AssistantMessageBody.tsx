import { memo, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import type { Message, ToolData } from '../utils/types'
import { normalizeChartMarkdown, parseMarkdown } from '../utils'
import { getAssistantMessageItems } from '../utils/assistantMessage'
import { ErrorCard } from './ErrorCard'
import { ProcessSummary } from './ProcessSummary'
import { buildAuthorizationHeaders, getStoredAuthToken } from '../utils/auth'
import { downloadChatFile, isChatFileLink } from '../utils/chatFiles'

/** 渲染 Markdown 正文。其他消息更新时复用已渲染的正文。
 *
 * Args:
 *   content: Markdown 正文。
 *   tools: 用来校正图表链接的工具结果。
 *   normalizeCharts: 是否校正助手生成的图表链接。
 */
export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  tools,
  normalizeCharts = false,
}: { content: string; tools?: ToolData[]; normalizeCharts?: boolean }) {
  const markdown = normalizeCharts ? normalizeChartMarkdown(content, tools) : content
  const [downloadError, setDownloadError] = useState('')
  return (
    <>
      <div
        className={styles.messageContent}
        dangerouslySetInnerHTML={{ __html: parseMarkdown(markdown) }}
        onClick={(event) => {
          if (!(event.target instanceof Element)) return
          const path = event.target.closest('a')?.getAttribute('href')
          if (!path || !isChatFileLink(path)) return
          event.preventDefault()
          setDownloadError('')
          void downloadChatFile(path, buildAuthorizationHeaders(getStoredAuthToken()))
            .catch((error: Error) => setDownloadError(error.message))
        }}
      />
      {downloadError && <p className={styles.composerImageError} role="alert">{downloadError}</p>}
    </>
  )
})

interface AssistantMessageBodyProps {
  msg: Message
  toolCallDurations?: Record<string, number>
  isProcessing: boolean
  showTokenUsage: boolean
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
 *   showTokenUsage: 是否展示 Token 用量，仅最新一条 assistant 消息为 true。
 *   onRecommendedQuestion: 推荐问题点击回调。
 *   onRetryMessage: 错误重试回调。
 */
export function AssistantMessageBody({
  msg,
  toolCallDurations,
  isProcessing,
  showTokenUsage,
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
  const tokenUsage = msg.tokenUsage

  return (
    <>
      <ProcessSummary
        msg={msg}
        reasoningBlocks={reasoningBlocks}
        toolCallDurations={toolCallDurations}
        isProcessing={isProcessing}
      />
      {visibleContentBlocks.map((block) => (
        <MarkdownMessage
          key={block.id}
          content={block.content}
          tools={msg.toolData}
          normalizeCharts
        />
      ))}
      {isProcessing && assistantItems.at(-1)?.type === 'content' && visibleContentBlocks.length > 0 && (
        <span className={styles.generationCursor} aria-hidden="true" />
      )}
      {!isProcessing && showTokenUsage && tokenUsage ? (
        <div
          className={styles.tokenUsage}
          aria-label="最新一次模型调用的 Token 用量"
          title="最新一次模型调用的 Token 用量；输入包含本次请求发送的全部上下文。"
        >
          <span className={styles.tokenUsageLabel}>本次 Token</span>
          <span className={styles.tokenUsageMetric}>
            <span>输入</span>
            <strong>{tokenUsage.inputTokens.toLocaleString('zh-CN')}</strong>
          </span>
          <span className={styles.tokenUsageDivider} aria-hidden="true">
            ·
          </span>
          <span className={styles.tokenUsageMetric}>
            <span>输出</span>
            <strong>{tokenUsage.outputTokens.toLocaleString('zh-CN')}</strong>
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
