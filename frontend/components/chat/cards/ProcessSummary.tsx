import { useEffect, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { Message, ReasoningBlock } from '../utils/types'
import { formatDuration } from '../utils'
import { getAssistantMessageItems } from '../utils/assistantMessage'
import { ReasoningCard } from './ReasoningCard'
import { ToolCard } from './ToolCard'

interface ProcessSummaryProps {
  msg: Message
  reasoningBlocks: ReasoningBlock[]
  toolCallDurations?: Record<string, number>
  isProcessing: boolean
}

/**
 * 展示 AI 消息的推理和工具调用摘要，并允许用户展开查看完整过程。
 *
 * Args:
 *   msg: 当前 AI 消息及其过程数据。
 *   reasoningBlocks: 当前消息的推理分段。
 *   toolCallDurations: 基于浏览器端时间计算的工具调用耗时映射。
 *   isProcessing: 当前消息是否仍在处理中。
 */
export function ProcessSummary({
  msg,
  reasoningBlocks,
  toolCallDurations,
  isProcessing,
}: ProcessSummaryProps) {
  const assistantItems = getAssistantMessageItems(msg)
  const processItems = assistantItems.filter(
    (item) => item.type === 'reasoning' || item.type === 'tool'
  ).filter((item) => {
    if (item.type === 'reasoning') {
      return reasoningBlocks.some((block) =>
        block.id === item.reasoningBlockId && block.content.trim()
      )
    }
    return msg.toolData?.some(
      (tool) => tool.toolCall.id === item.toolCallId
    )
  })
  const reasoningCount = processItems.filter(
    (item) => item.type === 'reasoning'
  ).length
  const toolCount = processItems.filter((item) => item.type === 'tool').length
  const summary = [
    reasoningCount > 0 ? `${reasoningCount} 段思考` : '',
    toolCount > 0 ? `${toolCount} 个工具调用` : '',
  ]
    .filter(Boolean)
    .join(' · ')
  const [now, setNow] = useState(() => Date.now())
  const totalDuration =
    msg.duration ??
    (msg.startedAt !== undefined ? Math.max(0, now - msg.startedAt) : 0)
  const hasFrontendTiming =
    msg.duration !== undefined || msg.startedAt !== undefined
  const durationSummary = hasFrontendTiming
    ? `总耗时 ${formatDuration(totalDuration)}`
    : ''
  const processMeta = [summary, durationSummary].filter(Boolean).join(' · ')
  /**
   * 使用浏览器时钟显示工具执行耗时，人工等待期间不计时。
   *
   * Args:
   *   toolCallId: 工具调用标识。
   */
  const getToolDuration = (toolCallId: string) => {
    const tool = msg.toolData?.find((data) => data.toolCall.id === toolCallId)
    if (!tool || tool.approvalStatus === 'pending' || tool.approvalStatus === 'rejected') return undefined
    if (tool.duration !== undefined) return tool.duration
    const hasResult = tool.toolOutput?.some((output) => output.kind !== 'decision')
    if (isProcessing && !hasResult && tool.startedAt !== undefined) {
      return Math.max(0, now - tool.startedAt)
    }
    return undefined
  }

  useEffect(() => {
    if (!isProcessing) return
    setNow(Date.now())
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isProcessing, msg.startedAt])

  const latestItem = assistantItems.at(-1)
  const latestTool = latestItem?.type === 'tool'
    ? msg.toolData?.find((tool) => tool.toolCall.id === latestItem.toolCallId)
    : undefined
  let activityLabel = '已完成'
  if (isProcessing) {
    activityLabel = '正在处理中...'
    if (latestItem?.type === 'content') activityLabel = '正在生成回答'
    if (latestItem?.type === 'reasoning') activityLabel = '正在思考'
    if (latestTool) {
      const isRetrieval = latestTool.toolCall.name === 'retrieve_context'
      const hasResult = latestTool.toolOutput?.some((output) => output.kind !== 'decision')
      const toolName = latestTool.toolCall.tool_display_name || latestTool.toolCall.name
      activityLabel = hasResult
        ? (isRetrieval ? '检索已返回' : '工具已返回')
        : latestTool.approvalStatus === 'pending' ? '等待审批'
          : latestTool.approvalStatus === 'rejected' ? '工具已拒绝'
            : latestTool.startedAt === undefined ? '正在准备工具参数'
              : (isRetrieval ? '正在检索知识库' : `正在执行 ${toolName}`)
    }
  }
  const hasProcess = processItems.length > 0
  const showCompletedRequest = !isProcessing && msg.thinkingRequest === 'completed'
  const showSummaryLabel = hasProcess || showCompletedRequest ||
    (isProcessing && msg.thinkingRequest === 'pending')

  const status = (
    <>
      <span
        className={`${styles.processSummaryStatus} ${
          isProcessing ? styles.processSummaryStatusActive : ''
        }`}
        aria-hidden="true"
      />
      <span
        className={`${styles.processSummaryLabel} ${
          isProcessing ? styles.processSummaryLabelActive : ''
        }`}
      >
        {showSummaryLabel ? '分析与执行' : activityLabel}
      </span>
      {showSummaryLabel && (
        <span className={styles.processSummaryActivity} aria-live="polite">
          {activityLabel}
        </span>
      )}
      <span className={styles.processSummaryMeta}>{processMeta}</span>
    </>
  )

  if (!hasProcess && !showCompletedRequest) {
    return isProcessing ? (
      <div className={styles.processSummary}>
        <div className={styles.processSummaryWaiting} role="status">{status}</div>
      </div>
    ) : null
  }

  return (
    <details className={styles.processSummary}>
      <summary className={styles.processSummaryHeader}>
        <span className={styles.processSummaryMark} aria-hidden="true">
          <span className={styles.processWhenClosed}>+</span>
          <span className={styles.processWhenOpen}>−</span>
        </span>
        {status}
        <span className={styles.processSummaryAction}>
          <span className={styles.processWhenClosed}>查看</span>
          <span className={styles.processWhenOpen}>收起</span>
        </span>
      </summary>
      <div className={styles.processSummaryDetails}>
        {!hasProcess && (
          <p className={styles.processEmpty}>本次未返回思考内容，也没有调用工具。</p>
        )}
        {processItems.map((item) => {
          if (item.type === 'reasoning') {
            const block = reasoningBlocks.find(
              (reasoningBlock) =>
                reasoningBlock.id === item.reasoningBlockId
            )
            return block ? (
              <ReasoningCard key={item.id} block={block}
                duration={block.duration ?? (isProcessing && block.startedAt !== undefined
                  ? Math.max(0, now - block.startedAt) : undefined)} />
            ) : null
          }

          const toolData = msg.toolData?.find(
            (data) => data.toolCall.id === item.toolCallId
          )
          return toolData ? (
            <ToolCard
              key={item.id}
              toolData={toolData}
              duration={getToolDuration(item.toolCallId)}
            />
          ) : null
        })}
      </div>
    </details>
  )
}
