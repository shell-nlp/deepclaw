import type { AssistantMessageItem, Message } from './types'

/**
 * 将 assistant 消息还原为按时间顺序排列的展示项。
 *
 * Args:
 *   msg: 待转换的 assistant 消息。
 *
 * Returns:
 *   推理、工具和正文展示项列表。
 */
export function getAssistantMessageItems(msg: Message): AssistantMessageItem[] {
  const reasoningItems = (
    msg.reasoningBlocks?.length
      ? msg.reasoningBlocks
      : msg.reasoningContent
        ? [{ id: `${msg.id}_reasoning_legacy`, content: msg.reasoningContent }]
        : []
  ).map((block) => ({
    id: `reasoning_item_${block.id}`,
    type: 'reasoning' as const,
    reasoningBlockId: block.id,
  }))
  const toolItems = (msg.toolData || []).map((toolData) => ({
    id: `tool_item_${toolData.toolCall.id}`,
    type: 'tool' as const,
    toolCallId: toolData.toolCall.id,
  }))
  const contentItems = (
    msg.contentBlocks?.length ? msg.contentBlocks
      : msg.content ? [{ id: `${msg.id}_content_legacy`, content: msg.content }] : []
  ).map((block) => ({
    id: `content_item_${block.id}`,
    type: 'content' as const,
    contentBlockId: block.id,
  }))
  const items = [...(msg.messageItems || [])]
  for (const item of [...reasoningItems, ...toolItems, ...contentItems]) {
    const exists = items.some((current) =>
      current.type === item.type && (
        current.type === 'reasoning' && item.type === 'reasoning'
          ? current.reasoningBlockId === item.reasoningBlockId
          : current.type === 'tool' && item.type === 'tool'
            ? current.toolCallId === item.toolCallId
            : current.type === 'content' && item.type === 'content'
              && current.contentBlockId === item.contentBlockId
      )
    )
    if (!exists) items.push(item)
  }
  return items
}
