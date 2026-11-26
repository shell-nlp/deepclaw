'use client'

import { useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from 'react'

import styles from '../ChatInterface.module.css'
import { InterruptPanel } from './interrupt/InterruptPanel'
import type { InterruptEditedAction } from './interrupt/utils'
import { AssistantMessageBody } from './cards/AssistantMessageBody'
import { UserMessageBody } from './cards/UserMessageBody'
import { AgentModeSwitcher } from './shared/AgentModeSwitcher'
import { ChatModelPicker } from './shared/ChatModelPicker'
import type { ChatModelOptions, ReasoningChoice } from './utils/reasoning'
import { DevicePicker } from './shared/DevicePicker'
import { CHAT_IMAGE_TYPES, readChatImage, type ChatImage } from './utils/chatImages'
import { CHAT_FILE_TYPES, uploadChatFile, type ChatFile } from './utils/chatFiles'
import type { RequestJson } from './management/schedules'
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

interface ComposerToggleProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

/**
 * 渲染输入框底部的能力开关胶囊。
 *
 * Args:
 *   label: 开关文案。
 *   checked: 开关是否开启。
 *   onChange: 开关状态变更回调。
 */
function ComposerToggle({ label, checked, onChange }: ComposerToggleProps) {
  return (
    <label className={styles.toggle}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <svg aria-hidden="true" className={styles.toggleIcon} fill="none" viewBox="0 0 24 24"
        stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">
        <circle cx="12" cy="12" r="8" />
        <path d="M4.3 12h15.4" />
        <path d="M12 4c2.3 2.6 2.3 13.4 0 16-2.3-2.6-2.3-13.4 0-16z" />
      </svg>
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
  draftFiles: ChatFile[]
  onDraftFilesChange: (files: ChatFile[]) => void
  fileDraftKey: string
  canAttachFiles: boolean
  canReadFiles: boolean
  requestJson: RequestJson
  withAuthHeaders: () => HeadersInit
  onDraftImagesChange: (images: ChatImage[]) => void
  chatModels: ChatModelOptions
  reasoningChoice: ReasoningChoice
  onReasoningChoiceChange: (choice: ReasoningChoice) => void
  selectedModelId: string
  onModelChange: (id: string) => void
  chatDisabled: boolean
  canUseChat: boolean
  internetSearch: boolean
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
  onNavigateToKnowledge: () => void
  onNavigateToFiles: () => void
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
  draftFiles,
  onDraftFilesChange,
  fileDraftKey,
  canAttachFiles,
  canReadFiles,
  requestJson,
  withAuthHeaders,
  onDraftImagesChange,
  chatModels,
  reasoningChoice,
  onReasoningChoiceChange,
  selectedModelId,
  onModelChange,
  chatDisabled,
  canUseChat,
  internetSearch,
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
  onNavigateToKnowledge,
  onNavigateToFiles,
  onAbortRequest,
  onSendMessage,
  onRecommendedQuestion,
  onRetryMessage,
}: ChatViewProps) {
  const imageInput = useRef<HTMLInputElement>(null)
  const [readingImages, setReadingImages] = useState(false)
  const [imageError, setImageError] = useState('')
  const [uploadingFileKey, setUploadingFileKey] = useState<string | null>(null)
  const uploadingFiles = uploadingFileKey === fileDraftKey
  const currentFileDraftKey = useRef(fileDraftKey)
  currentFileDraftKey.current = fileDraftKey
  const busyWithAttachments = readingImages || uploadingFiles

  /** 上传所选文档并在当前会话保留已成功的附件。Args: files 为本次选择的文档。 */
  const addFiles = async (files: File[]) => {
    if (!files.length || !canAttachFiles || uploadingFileKey !== null) return
    if (files.length + draftFiles.length > 4) {
      setImageError('每条消息最多添加 4 个文档。')
      return
    }
    setImageError('')
    setUploadingFileKey(fileDraftKey)
    const uploaded = [...draftFiles]
    const headers = withAuthHeaders()
    try {
      for (const file of files) {
        const attachment = await uploadChatFile(file, headers)
        const index = uploaded.findIndex((item) => item.file_id === attachment.file_id)
        if (index === -1) uploaded.push(attachment)
        else if (attachment.reused) uploaded[index] = attachment
        if (currentFileDraftKey.current !== fileDraftKey) break
        onDraftFilesChange([...uploaded])
      }
    } catch (error) {
      if (currentFileDraftKey.current === fileDraftKey) {
        setImageError(error instanceof Error ? error.message : '文件上传失败。')
      }
    } finally {
      setUploadingFileKey(null)
    }
  }

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
                  <UserMessageBody message={msg} />
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
          <input ref={imageInput} type="file" hidden multiple accept={canAttachFiles ? CHAT_IMAGE_TYPES + ',' + CHAT_FILE_TYPES : CHAT_IMAGE_TYPES}
            onChange={(event) => {
              const files = Array.from(event.currentTarget.files ?? [])
              void addImages(files.filter((file) => file.type.startsWith('image/')))
              void addFiles(files.filter((file) => !file.type.startsWith('image/')))
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
          {(draftFiles.length > 0 || uploadingFiles) && <div className={styles.composerImages}>
            {draftFiles.map((file) => (
              <span key={file.file_id} className={styles.composerFile} title={file.name}>
                <span>{file.name}{file.reused && ' · 已复用'}</span>
                <button type="button" disabled={uploadingFiles} aria-label={'移除 ' + file.name}
                  onClick={() => onDraftFilesChange(draftFiles.filter((item) => item.file_id !== file.file_id))}>×</button>
              </span>
            ))}
            {uploadingFiles && <span className={styles.composerFile} role="status">正在上传文档…</span>}
          </div>}
          {imageError && <p className={styles.composerImageError} role="alert">{imageError}</p>}
          <textarea
            ref={textareaRef}
            className={styles.input}
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (busyWithAttachments && event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) event.preventDefault()
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
              <button type="button" className={styles.composerAddImage} aria-label={canAttachFiles ? '添加图片或文档' : '上传图片'}
                title={canAttachFiles ? '添加图片或文档' : '上传图片'}
                disabled={busyWithAttachments || isProcessing} onClick={() => imageInput.current?.click()}>
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
                favoriteFiles={canReadFiles ? {
                  files: draftFiles,
                  onChange: onDraftFilesChange,
                  onNavigate: onNavigateToFiles,
                  requestJson,
                  disabled: busyWithAttachments || isProcessing,
                } : undefined}
              />
              <ComposerToggle
                label="联网"
                checked={internetSearch}
                onChange={onInternetSearchChange}
              />
            </div>
            <div className={styles.composerActions}>
              <ChatModelPicker models={chatModels} modelId={selectedModelId} choice={reasoningChoice}
                onModelChange={onModelChange} onChoiceChange={onReasoningChoiceChange} />
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
                disabled={busyWithAttachments || (!inputValue.trim() && !draftImages.length && !draftFiles.length) || chatDisabled}
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
