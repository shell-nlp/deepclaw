import type { AssistantMessageItem, Message } from '../../chat-interface/types'

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
  if (msg.messageItems?.length) return msg.messageItems

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
  const contentItems = msg.content
    ? [
        {
          id: `${msg.id}_content_legacy_item`,
          type: 'content' as const,
          contentBlockId: `${msg.id}_content_legacy`,
        },
      ]
    : []

  return [...reasoningItems, ...toolItems, ...contentItems]
}
