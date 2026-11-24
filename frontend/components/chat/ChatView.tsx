'use client'

import { useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from 'react'

import styles from '../ChatInterface.module.css'
import { InterruptPanel } from './interrupt/InterruptPanel'
import type { InterruptEditedAction } from './interrupt/utils'
import { AssistantMessageBody, MarkdownMessage } from './cards/AssistantMessageBody'
import { AgentModeSwitcher } from './shared/AgentModeSwitcher'
import { DevicePicker } from './shared/DevicePicker'
import { CHAT_IMAGE_TYPES, readChatImage, type ChatImage } from './utils/chatImages'
import type { ClientDevice } from './hooks/useDevices'
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
  notifications?: ReactNode
  devices?: ClientDevice[]
  selectedDeviceId?: string
  onDeviceChange?: (id: string) => void
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
  draftImages: ChatImage[]
  onDraftImagesChange: (images: ChatImage[]) => void
  chatModels: { items: { id: string; name: string }[]; default_id: string | null }
  selectedModelId: string
  onModelChange: (id: string) => void
  chatDisabled: boolean
  canUseChat: boolean
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
  notifications,
  devices = [],
  selectedDeviceId = '',
  onDeviceChange,
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
  draftImages,
  onDraftImagesChange,
  chatModels,
  selectedModelId,
  onModelChange,
  chatDisabled,
  canUseChat,
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
  const imageInput = useRef<HTMLInputElement>(null)
  const [readingImages, setReadingImages] = useState(false)
  const [imageError, setImageError] = useState('')
  const defaultModel = chatModels.items.find((model) => model.id === chatModels.default_id)

  /** 读取并预览本次选择的图片。Args: files 为本地文件选项。 */
  const addImages = async (files: File[]) => {
    if (!files.length || readingImages) return
    setImageError('')
    if (files.length + draftImages.length > 4) {
      setImageError('每条消息最多添加 4 张图片。')
      return
    }
    const existingBytes = draftImages.reduce((total, image) => {
      const encoded = image.url.slice(image.url.indexOf(',') + 1)
      return total + encoded.length * 3 / 4 - (encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0)
    }, 0)
    if (files.reduce((total, file) => total + file.size, existingBytes) > 10 * 1024 * 1024) {
      setImageError('每条消息的图片合计最多 10 MB。')
      return
    }
    setReadingImages(true)
    try {
      onDraftImagesChange([...draftImages, ...await Promise.all(files.map(readChatImage))])
    } catch (error) {
      setImageError(error instanceof Error ? error.message : '图片读取失败。')
    } finally {
      setReadingImages(false)
    }
  }

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
          {notifications}
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
                  {msg.images?.length ? <div className={styles.chatMessageImages}>
                    {msg.images.map((image, index) => <img key={index} src={image.url} alt={image.name} />)}
                  </div> : null}
                  <MarkdownMessage content={msg.content} />
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
          <input ref={imageInput} type="file" hidden multiple accept={CHAT_IMAGE_TYPES}
            onChange={(event) => {
              void addImages(Array.from(event.currentTarget.files ?? []))
              event.currentTarget.value = ''
            }} />
          {draftImages.length > 0 && <div className={styles.composerImages}>
            {draftImages.map((image, index) => (
              <div key={index} className={styles.composerImage} title={image.name}>
                <img src={image.url} alt={image.name} />
                <button type="button" disabled={readingImages} aria-label={'移除 ' + image.name}
                  onClick={() => { setImageError(''); onDraftImagesChange(draftImages.filter((_, i) => i !== index)) }}>×</button>
              </div>
            ))}
          </div>}
          {imageError && <p className={styles.composerImageError} role="alert">{imageError}</p>}
          <textarea
            ref={textareaRef}
            className={styles.input}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (readingImages && event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) event.preventDefault()
              else onKeyDown(event)
            }}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith('image/'))
              if (files.length) void addImages(files)
            }}
            placeholder={
              !canUseChat
                ? '当前账号没有发送消息的权限。'
                : isKnowledgeMode
                ? chatDisabled
                  ? '请先在知识管理中选择一个知识库...'
                  : '输入您的知识库问题...'
                : '给 DeepClaw 发送消息...'
            }
            rows={1}
          />
          <div className={styles.composerFooter}>
            <div className={styles.toggles}>
              <button type="button" className={styles.composerAddImage} aria-label="上传图片"
                title="上传图片" disabled={readingImages || isProcessing} onClick={() => imageInput.current?.click()}>
                <span aria-hidden="true">+</span>
              </button>
              {!isKnowledgeMode && onDeviceChange && <DevicePicker devices={devices} value={selectedDeviceId} disabled={isProcessing} onChange={onDeviceChange}/>}
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
            <div className={styles.composerActions}>
              <label className={styles.composerModel}>
                <select aria-label="选择聊天模型" value={selectedModelId} onChange={(event) => onModelChange(event.target.value)}>
                  <option value="">{defaultModel ? defaultModel.name + '（默认）' : '默认模型'}</option>
                  {chatModels.items.filter((model) => model.id !== chatModels.default_id || model.id === selectedModelId).map((model) =>
                    <option key={model.id} value={model.id}>{model.name}</option>
                  )}
                </select>
              </label>
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
                disabled={readingImages || (!inputValue.trim() && !draftImages.length) || chatDisabled}
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
        </div>
        <p className={styles.composerDisclaimer}>内容由 AI 生成，请仔细甄别</p>
      </div>
    </>
  )
}
