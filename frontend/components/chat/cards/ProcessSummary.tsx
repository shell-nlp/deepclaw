import { useEffect, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { Message, ReasoningBlock } from '../../chat-interface/types'
import { formatDuration } from '../../chat-interface/utils'
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
  const [expanded, setExpanded] = useState(false)
  const processItems = getAssistantMessageItems(msg).filter(
    (item) => item.type === 'reasoning' || item.type === 'tool'
  )
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
  const getToolDuration = (toolCallId: string) =>
    msg.toolData?.find((data) => data.toolCall.id === toolCallId)?.duration ??
    toolCallDurations?.[toolCallId]

  const activitySteps = processItems.map((item) => {
    if (item.type === 'reasoning') return '正在思考中...'
    const toolData = msg.toolData?.find(
      (data) => data.toolCall.id === item.toolCallId
    )
    const toolName =
      toolData?.toolCall.tool_display_name || toolData?.toolCall.name || '工具'
    return `执行${toolName}`
  })
  const [activityIndex, setActivityIndex] = useState(0)

  useEffect(() => {
    if (!isProcessing || msg.startedAt === undefined) return
    setNow(Date.now())
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isProcessing, msg.startedAt])

  useEffect(() => {
    if (!isProcessing || activitySteps.length <= 1) {
      setActivityIndex(0)
      return
    }
    const timer = window.setInterval(() => {
      setActivityIndex((current) => (current + 1) % activitySteps.length)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [activitySteps.length, isProcessing])

  const activityLabel = isProcessing
    ? activitySteps[activityIndex % activitySteps.length] || '正在处理中...'
    : '已完成'

  if (processItems.length === 0 && !isProcessing) return null

  return (
    <section className={styles.processSummary}>
      <button
        type="button"
        className={styles.processSummaryHeader}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className={styles.processSummaryMark} aria-hidden="true">
          {expanded ? '−' : '+'}
        </span>
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
          分析与执行
        </span>
        <span className={styles.processSummaryActivity} aria-live="polite">
          {activityLabel}
        </span>
        <span className={styles.processSummaryMeta}>{processMeta}</span>
        <span className={styles.processSummaryAction}>
          {expanded ? '收起' : '查看'}
        </span>
      </button>
      {expanded && (
        <div className={styles.processSummaryDetails}>
          {processItems.map((item) => {
            if (item.type === 'reasoning') {
              const block = reasoningBlocks.find(
                (reasoningBlock) =>
                  reasoningBlock.id === item.reasoningBlockId
              )
              return block ? (
                <ReasoningCard key={item.id} block={block} />
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
      )}
    </section>
  )
}
