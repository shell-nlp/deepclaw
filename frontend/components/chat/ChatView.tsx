'use client'

import type { KeyboardEvent, ReactNode, Ref } from 'react'

import styles from '../ChatInterface.module.css'
import { InterruptPanel } from './interrupt/InterruptPanel'
import type { InterruptEditedAction } from './interrupt/utils'
import { AssistantMessageBody } from './cards/AssistantMessageBody'
import { AgentModeSwitcher } from './shared/AgentModeSwitcher'
import {
  KnowledgeBasePicker,
} from './shared/KnowledgeBasePicker'
import type {
  ChatModeOption,
  ChatStatus,
  InterruptData,
  KnowledgeBase,
  Message,
} from './utils/types'
import {
  parseMarkdown,
} from './utils'

function formatMessageTime(msg: Message): string {
  const timestamp = msg.createdAt ?? msg.startedAt
  return new Date(timestamp ?? Date.now()).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

type ComposerToggleIconName = 'internet' | 'thinking'

/**
 * 渲染输入框能力开关的图标。
 *
 * Args:
 *   name: 图标名称。
 */
function ComposerToggleIcon({ name }: { name: ComposerToggleIconName }) {
  const paths: Record<ComposerToggleIconName, ReactNode> = {
    internet: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M4.3 12h15.4" />
        <path d="M12 4c2.3 2.6 2.3 13.4 0 16-2.3-2.6-2.3-13.4 0-16z" />
      </>
    ),
    thinking: (
      <>
        <path d="m12 4.4 1.8 4.2 4.2 1.8-4.2 1.8-1.8 4.2-1.8-4.2L6 10.4l4.2-1.8z" />
        <path d="m18.4 15.6.7 1.7 1.7.7-1.7.7-.7 1.7-.7-1.7-1.7-.7 1.7-.7z" />
      </>
    ),
  }

  return (
    <svg
      aria-hidden="true"
      className={styles.toggleIcon}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  )
}

interface ComposerToggleProps {
  label: string
  iconName: ComposerToggleIconName
  checked: boolean
  onChange: (checked: boolean) => void
}

/**
 * 渲染输入框底部的能力开关胶囊。
 *
 * Args:
 *   label: 开关文案。
 *   iconName: 开关图标名称。
 *   checked: 开关是否开启。
 *   onChange: 开关状态变更回调。
 */
function ComposerToggle({ label, iconName, checked, onChange }: ComposerToggleProps) {
  return (
    <label className={styles.toggle}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <ComposerToggleIcon name={iconName} />
      <span className={styles.toggleLabel}>{label}</span>
    </label>
  )
}

interface ChatViewProps {
  messages: Message[]
  sessionId: string
  chatModeOptions: ChatModeOption[]
  activeChatModeId: string
  mcpStatusLabel: string
  status: ChatStatus
  isProcessing: boolean
  isKnowledgeMode: boolean
  knowledgeBaseOptions: KnowledgeBase[]
  selectedKnowledgeBaseIds: string[]
  knowledgePickerOpen: boolean
  loadingKnowledgeBaseOptions: boolean
  showInterrupt: boolean
  interruptData: InterruptData | null
  inputValue: string
  chatDisabled: boolean
  internetSearch: boolean
  deepThinking: boolean
  currentAssistantMessageId: string | null
  chatContainerRef: Ref<HTMLDivElement>
  onChatScroll: () => void
  textareaRef: Ref<HTMLTextAreaElement>
  toolCallDurations?: Record<string, number>
  onClearChat: () => void
  onInterruptAction: (
    decision: 'approve' | 'reject' | 'edit',
    editedActions?: InterruptEditedAction[]
  ) => void | Promise<void>
  onAskUserResponse: (answer: string) => void | Promise<void>
  onInputChange: (value: string) => void
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  onKnowledgePickerOpenChange: (open: boolean) => void
  onKnowledgeSelectionChange: (ids: string[]) => void
  onChatModeChange: (optionId: string) => void
  onInternetSearchChange: (checked: boolean) => void
  onDeepThinkingChange: (checked: boolean) => void
  onNavigateToKnowledge: () => void
  onAbortRequest: () => void
  onSendMessage: () => void | Promise<void>
  onRecommendedQuestion: (question: string) => void | Promise<void>
  onRetryMessage: (messageId: string) => void | Promise<void>
}

export function ChatView({
  messages,
  sessionId,
  chatModeOptions,
  activeChatModeId,
  mcpStatusLabel,
  status,
  isProcessing,
  isKnowledgeMode,
  knowledgeBaseOptions,
  selectedKnowledgeBaseIds,
  knowledgePickerOpen,
  loadingKnowledgeBaseOptions,
  showInterrupt,
  interruptData,
  inputValue,
  chatDisabled,
  internetSearch,
  deepThinking,
  currentAssistantMessageId,
  chatContainerRef,
  onChatScroll,
  textareaRef,
  toolCallDurations,
  onClearChat,
  onInterruptAction,
  onAskUserResponse,
  onInputChange,
  onKeyDown,
  onKnowledgePickerOpenChange,
  onKnowledgeSelectionChange,
  onChatModeChange,
  onInternetSearchChange,
  onDeepThinkingChange,
  onNavigateToKnowledge,
  onAbortRequest,
  onSendMessage,
  onRecommendedQuestion,
  onRetryMessage,
}: ChatViewProps) {
  const latestAssistantMessageId = messages.reduce<string | null>(
    (latestId, message) =>
      message.role === 'ai' ? message.id : latestId,
    null
  )

  return (
    <>
      <div className={styles.sessionBar}>
        <div className={styles.sessionInfo}>
          <span className={styles.sessionLabel}>会话</span>
          <code className={styles.sessionId}>{sessionId.slice(0, 8)}...</code>
          <span className={styles.sessionLabel}>模式</span>
          <AgentModeSwitcher
            options={chatModeOptions}
            value={activeChatModeId}
            disabled={isProcessing}
            onChange={onChatModeChange}
          />
          <span className={styles.sessionLabel}>MCP</span>
          <code className={styles.sessionId}>{mcpStatusLabel}</code>
        </div>
        <div className={styles.statusArea}>
          <span className={`${styles.statusDot} ${styles[status]}`} />
          <span className={styles.statusText}>
            {status === 'ready' ? '就绪' : status === 'connecting' ? '处理中' : '错误'}
          </span>
          <button className={styles.clearBtn} onClick={onClearChat}>
            新建/清空会话
          </button>
        </div>
      </div>

      <div
        className={styles.chatContainer}
        ref={chatContainerRef}
        onScroll={onChatScroll}
      >
        {messages.length === 0 ? (
          <div className={styles.welcome}>
            <div className={styles.welcomeIcon}>DC</div>
            <h2>欢迎使用 DeepClaw</h2>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`${styles.message} ${styles[msg.role]}`}>
              {msg.role === 'user' ? (
                <>
                  <div className={styles.messageHeader}>
                    <div className={styles.avatar}>U</div>
                    <span className={styles.author}>用户</span>
                    <span className={styles.time}>
                      {formatMessageTime(msg)}
                    </span>
                  </div>
                  <div
                    className={styles.messageContent}
                    dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
                  />
                </>
              ) : (
                <>
                  <div className={styles.messageHeader}>
                    <div className={`${styles.avatar} ${styles.ai}`}>AI</div>
                    <span className={styles.author}>AI 助手</span>
                    <span className={styles.time}>
                      {formatMessageTime(msg)}
                    </span>
                  </div>
                  <AssistantMessageBody
                    msg={msg}
                    toolCallDurations={toolCallDurations}
                    isProcessing={isProcessing && msg.id === currentAssistantMessageId}
                    showTokenUsage={msg.id === latestAssistantMessageId}
                    onRecommendedQuestion={onRecommendedQuestion}
                    onRetryMessage={onRetryMessage}
                  />
                </>
              )}
            </div>
          ))
        )}

        <InterruptPanel showInterrupt={showInterrupt} interruptData={interruptData} onInterruptAction={onInterruptAction} onAskUserResponse={onAskUserResponse} />

        {isProcessing && messages[messages.length - 1]?.role !== 'ai' && (
          <div className={`${styles.message} ${styles.ai}`}>
            <div className={styles.messageHeader}>
              <div className={`${styles.avatar} ${styles.ai}`}>AI</div>
              <span className={styles.author}>AI 助手</span>
            </div>
            <div className={styles.typingIndicator}>
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
      </div>

      <div className={styles.inputArea}>
        <div className={styles.inputContainer}>
          <textarea
            ref={textareaRef}
            className={styles.input}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              isKnowledgeMode
                ? chatDisabled
                  ? '请先在知识管理中选择一个知识库...'
                  : '输入您的知识库问题...'
                : '给 DeepClaw 发送消息...'
            }
            rows={1}
          />
          <div className={styles.composerFooter}>
            <div className={styles.toggles}>
              <KnowledgeBasePicker
                open={knowledgePickerOpen}
                options={knowledgeBaseOptions}
                selectedIds={selectedKnowledgeBaseIds}
                loading={loadingKnowledgeBaseOptions}
                disabled={status === 'connecting'}
                onOpenChange={onKnowledgePickerOpenChange}
                onSelectionChange={onKnowledgeSelectionChange}
                onNavigateToKnowledge={onNavigateToKnowledge}
              />
              <ComposerToggle
                label="联网"
                iconName="internet"
                checked={internetSearch}
                onChange={onInternetSearchChange}
              />
              <ComposerToggle
                label="思考"
                iconName="thinking"
                checked={deepThinking}
                onChange={onDeepThinkingChange}
              />
            </div>
            {isProcessing ? (
              <button
                className={styles.abortBtn}
                onClick={onAbortRequest}
                aria-label="中断当前回答"
                title="中断"
              >
                <svg
                  aria-hidden="true"
                  className={styles.stopIcon}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                >
                  <rect x="8.5" y="8.5" width="7" height="7" rx="1.8" fill="currentColor" />
                </svg>
              </button>
            ) : (
              <button
                className={styles.sendBtn}
                onClick={() => void onSendMessage()}
                disabled={!inputValue.trim() || chatDisabled}
                aria-label="发送消息"
                title="发送"
              >
                <svg
                  aria-hidden="true"
                  className={styles.sendIcon}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.9"
                >
                  <path d="M12 19V5" />
                  <path d="m5.8 11.2 6.2-6.2 6.2 6.2" />
                </svg>
              </button>
            )}
          </div>
        </div>
        <p className={styles.composerDisclaimer}>内容由 AI 生成，请仔细甄别</p>
      </div>
    </>
  )
}
