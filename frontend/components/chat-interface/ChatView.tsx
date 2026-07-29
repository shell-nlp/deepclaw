'use client'

import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, Ref } from 'react'

import styles from '../ChatInterface.module.css'
import { ReasoningCard } from './ReasoningCard'
import { ToolCard } from './ToolCard'
import type {
  AssistantMessageItem,
  ChatStatus,
  InterruptData,
  Message,
} from './types'
import { getToolIcon, parseMarkdown } from './utils'

type InterruptDecision = 'approve' | 'reject' | 'edit'
type InterruptActionRequest = NonNullable<InterruptData>['action_requests'][number]
type InterruptEditedAction = { name: string; args: Record<string, unknown> }
type InterruptArgPath = Array<string | number>

interface ChatViewProps {
  messages: Message[]
  sessionId: string
  userId: string
  chatModeLabel: string
  mcpStatusLabel: string
  status: ChatStatus
  isProcessing: boolean
  useKnowledgeBase: boolean
  selectedKnowledgeBaseName: string | null
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
  onInputChange: (value: string) => void
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  onKnowledgeBaseToggle: (checked: boolean) => void
  onInternetSearchChange: (checked: boolean) => void
  onDeepThinkingChange: (checked: boolean) => void
  onNavigateToKnowledge: () => void
  onAbortRequest: () => void
  onSendMessage: () => void | Promise<void>
  onRecommendedQuestion: (question: string) => void | Promise<void>
}

function getAssistantMessageItems(msg: Message): AssistantMessageItem[] {
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

function AssistantMessageBody({
  msg,
  toolCallDurations,
  onRecommendedQuestion,
}: {
  msg: Message
  toolCallDurations?: Record<string, number>
  onRecommendedQuestion: (question: string) => void | Promise<void>
}) {
  const reasoningBlocks =
    msg.reasoningBlocks?.length
      ? msg.reasoningBlocks
      : msg.reasoningContent
        ? [{ id: `${msg.id}_reasoning_legacy`, content: msg.reasoningContent }]
        : []
  const contentBlocks =
    msg.contentBlocks?.length
      ? msg.contentBlocks
      : msg.content
        ? [{ id: `${msg.id}_content_legacy`, content: msg.content }]
        : []

  return (
    <>
      {getAssistantMessageItems(msg).map((item) => {
        if (item.type === 'reasoning') {
          const block = reasoningBlocks.find(
            (reasoningBlock) => reasoningBlock.id === item.reasoningBlockId
          )
          return block ? (
            <ReasoningCard key={item.id} block={block} />
          ) : null
        }

        if (item.type === 'tool') {
          const toolData = msg.toolData?.find(
            (data) => data.toolCall.id === item.toolCallId
          )
          return toolData ? (
            <ToolCard
              key={item.id}
              toolData={toolData}
              duration={toolCallDurations?.[item.toolCallId]}
            />
          ) : null
        }

        const block = contentBlocks.find(
          (contentBlock) => contentBlock.id === item.contentBlockId
        )
        return block ? (
          <div
            key={item.id}
            className={styles.messageContent}
            dangerouslySetInnerHTML={{ __html: parseMarkdown(block.content) }}
          />
        ) : null
      })}
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
    </>
  )
}

function getInterruptActionArgs(
  action: InterruptActionRequest
): Record<string, unknown> {
  return action.args ?? action.arguments ?? {}
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function cloneInterruptArgs(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
}

function updateValueAtPath(
  value: unknown,
  path: InterruptArgPath,
  nextValue: unknown
): unknown {
  if (path.length === 0) return nextValue

  const [head, ...rest] = path
  if (Array.isArray(value)) {
    const clone = [...value]
    const index = Number(head)
    clone[index] = updateValueAtPath(clone[index], rest, nextValue)
    return clone
  }

  const clone = isRecord(value) ? { ...value } : {}
  clone[String(head)] = updateValueAtPath(clone[String(head)], rest, nextValue)
  return clone
}

function formatArgLabel(key: string | number): string {
  return typeof key === 'number' ? `#${key + 1}` : key
}

function isInterruptDecisionAllowed(
  interruptData: InterruptData,
  actionIndex: number,
  decision: InterruptDecision
): boolean {
  const action = interruptData?.action_requests?.[actionIndex]
  const configs = interruptData?.review_configs || []
  const config =
    configs[actionIndex] ||
    configs.find((item) => item.action_name === action?.name)

  return config ? config.allowed_decisions.includes(decision) : true
}

function isDecisionAllowedForAllActions(
  interruptData: InterruptData,
  decision: InterruptDecision
): boolean {
  const actionCount = interruptData?.action_requests?.length || 0
  if (actionCount === 0) return false

  return interruptData.action_requests.every((_, index) =>
    isInterruptDecisionAllowed(interruptData, index, decision)
  )
}

interface InterruptArgFieldsProps {
  value: unknown
  path: InterruptArgPath
  label?: string
  disabled: boolean
  inputRef?: (element: HTMLInputElement | HTMLTextAreaElement | null) => void
  onChange: (path: InterruptArgPath, value: unknown) => void
}

function InterruptArgFields({
  value,
  path,
  label,
  disabled,
  inputRef,
  onChange,
}: InterruptArgFieldsProps) {
  if (Array.isArray(value)) {
    return (
      <div className={styles.interruptArgGroup}>
        {label && <div className={styles.interruptArgGroupLabel}>{label}</div>}
        {value.length > 0 ? (
          value.map((item, index) => (
            <InterruptArgFields
              key={`${path.join('.')}.${index}`}
              value={item}
              path={[...path, index]}
              label={formatArgLabel(index)}
              disabled={disabled}
              onChange={onChange}
            />
          ))
        ) : (
          <span className={styles.interruptArgEmpty}>空列表</span>
        )}
      </div>
    )
  }

  if (isRecord(value)) {
    const entries = Object.entries(value)

    return (
      <div className={styles.interruptArgGroup}>
        {label && <div className={styles.interruptArgGroupLabel}>{label}</div>}
        {entries.length > 0 ? (
          entries.map(([key, item], index) => (
            <InterruptArgFields
              key={`${path.join('.')}.${key}`}
              value={item}
              path={[...path, key]}
              label={formatArgLabel(key)}
              disabled={disabled}
              inputRef={path.length === 0 && index === 0 ? inputRef : undefined}
              onChange={onChange}
            />
          ))
        ) : (
          <span className={styles.interruptArgEmpty}>空对象</span>
        )}
      </div>
    )
  }

  if (typeof value === 'boolean') {
    return (
      <label className={styles.interruptFormField}>
        <span className={styles.interruptFieldLabel}>{label}</span>
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptCheckbox}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={(event) => onChange(path, event.currentTarget.checked)}
        />
      </label>
    )
  }

  if (typeof value === 'number') {
    return (
      <label className={styles.interruptFormField}>
        <span className={styles.interruptFieldLabel}>{label}</span>
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptInput}
          type="number"
          value={Number.isFinite(value) ? value : ''}
          disabled={disabled}
          onChange={(event) => {
            const raw = event.currentTarget.value
            onChange(path, raw === '' ? null : Number(raw))
          }}
        />
      </label>
    )
  }

  const textValue = value == null ? '' : String(value)
  const isLongText = textValue.length > 80 || textValue.includes('\n')

  return (
    <label className={styles.interruptFormField}>
      <span className={styles.interruptFieldLabel}>{label}</span>
      {isLongText ? (
        <textarea
          ref={inputRef as ((element: HTMLTextAreaElement | null) => void) | undefined}
          className={styles.interruptInput}
          value={textValue}
          disabled={disabled}
          rows={4}
          onChange={(event) => onChange(path, event.currentTarget.value)}
        />
      ) : (
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptInput}
          type="text"
          value={textValue}
          disabled={disabled}
          onChange={(event) => onChange(path, event.currentTarget.value)}
        />
      )}
    </label>
  )
}

export function ChatView({
  messages,
  sessionId,
  userId,
  chatModeLabel,
  mcpStatusLabel,
  status,
  isProcessing,
  useKnowledgeBase,
  selectedKnowledgeBaseName,
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
  onInputChange,
  onKeyDown,
  onKnowledgeBaseToggle,
  onInternetSearchChange,
  onDeepThinkingChange,
  onNavigateToKnowledge,
  onAbortRequest,
  onSendMessage,
  onRecommendedQuestion,
}: ChatViewProps) {
  const [isEditingInterruptArgs, setIsEditingInterruptArgs] = useState(false)
  const [interruptArgsDrafts, setInterruptArgsDrafts] = useState<
    Record<string, unknown>[]
  >([])
  const interruptEditorRefs = useRef<
    Array<HTMLInputElement | HTMLTextAreaElement | null>
  >([])
  const canEditInterrupt =
    interruptData && isDecisionAllowedForAllActions(interruptData, 'edit')

  useEffect(() => {
    setIsEditingInterruptArgs(false)
    setInterruptArgsDrafts(
      interruptData?.action_requests.map((action) =>
        cloneInterruptArgs(getInterruptActionArgs(action))
      ) || []
    )
    interruptEditorRefs.current = []
  }, [interruptData])

  const updateInterruptArgDraft = (
    actionIndex: number,
    path: InterruptArgPath,
    value: unknown
  ) => {
    setInterruptArgsDrafts((prev) =>
      prev.map((draft, index) =>
        index === actionIndex
          ? (updateValueAtPath(draft, path, value) as Record<string, unknown>)
          : draft
      )
    )
  }

  const handleEditInterrupt = () => {
    if (!interruptData || !canEditInterrupt) return

    if (!isEditingInterruptArgs) {
      setIsEditingInterruptArgs(true)
      window.setTimeout(() => {
        interruptEditorRefs.current[0]?.focus()
      }, 0)
      return
    }

    void onInterruptAction(
      'edit',
      interruptData.action_requests.map((action, index) => ({
        name: action.name,
        args: interruptArgsDrafts[index] || getInterruptActionArgs(action),
      }))
    )
  }

  const interruptPanel =
    showInterrupt && interruptData ? (
      <div className={styles.interruptPanel}>
        <div className={styles.interruptHeader}>
          <span>需要人工确认</span>
        </div>
        <div className={styles.interruptContent}>
          {interruptData.action_requests?.map((action, index) => (
            <div key={index} className={styles.interruptAction}>
              <div className={styles.interruptActionHeader}>
                <span className={styles.interruptToolIcon}>
                  {getToolIcon(action.name)}
                </span>
                <span className={styles.interruptToolName}>{action.name}</span>
              </div>
              {action.description && (
                <p className={styles.interruptDescription}>{action.description}</p>
              )}
              <div className={styles.interruptArgsSection}>
                <span className={styles.interruptSectionLabel}>参数</span>
                <InterruptArgFields
                  value={interruptArgsDrafts[index] || getInterruptActionArgs(action)}
                  path={[]}
                  disabled={
                    !isEditingInterruptArgs ||
                    !isInterruptDecisionAllowed(interruptData, index, 'edit')
                  }
                  inputRef={(element) => {
                    interruptEditorRefs.current[index] = element
                  }}
                  onChange={(path, value) =>
                    updateInterruptArgDraft(index, path, value)
                  }
                />
              </div>
            </div>
          ))}
        </div>
        <div className={styles.interruptButtons}>
          <button
            className={`${styles.interruptBtn} ${styles.approve}`}
            onClick={() => void onInterruptAction('approve')}
            disabled={!isDecisionAllowedForAllActions(interruptData, 'approve')}
          >
            批准
          </button>
          <button
            className={`${styles.interruptBtn} ${styles.edit}`}
            onClick={handleEditInterrupt}
            disabled={!canEditInterrupt}
          >
            {isEditingInterruptArgs ? '提交编辑' : '编辑参数'}
          </button>
          <button
            className={`${styles.interruptBtn} ${styles.reject}`}
            onClick={() => void onInterruptAction('reject')}
            disabled={!isDecisionAllowedForAllActions(interruptData, 'reject')}
          >
            拒绝
          </button>
        </div>
      </div>
    ) : null

  return (
    <>
      <div className={styles.sessionBar}>
        <div className={styles.sessionInfo}>
          <span className={styles.sessionLabel}>会话</span>
          <code className={styles.sessionId}>{sessionId.slice(0, 8)}...</code>
          <span className={styles.sessionDivider}>|</span>
          <span className={styles.sessionLabel}>用户</span>
          <code className={styles.sessionId}>{userId}</code>
          <span className={styles.sessionDivider}>|</span>
          <span className={styles.sessionLabel}>模式</span>
          <code className={styles.sessionId}>{chatModeLabel}</code>
          <span className={styles.sessionDivider}>|</span>
          <span className={styles.sessionLabel}>知识库</span>
          <code className={styles.sessionId}>
            {useKnowledgeBase ? selectedKnowledgeBaseName || '未选择' : '未启用'}
          </code>
          <span className={styles.sessionDivider}>|</span>
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
            <div className={styles.welcomeIcon}>KB</div>
            <h2>欢迎使用 DeepClaw</h2>
            <p>
              默认直接使用 Agent 对话。开启知识库后，将切到 RAG 图检索，并且必须选择一个知识库。
            </p>
            <div className={styles.exampleQueries}>
              <button onClick={() => onInputChange('请帮我总结一下今天要做的事情。')}>
                通用问答
              </button>
              <button
                onClick={() =>
                  onInputChange('请列出文档中涉及的重要实体和它们之间的关系。')
                }
              >
                提取实体关系
              </button>
              <button onClick={onNavigateToKnowledge}>进入知识管理</button>
            </div>
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
                      {new Date().toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
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
                      {new Date().toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <AssistantMessageBody
                    msg={msg}
                    toolCallDurations={toolCallDurations}
                    onRecommendedQuestion={onRecommendedQuestion}
                  />
                  {isProcessing &&
                    msg.id === currentAssistantMessageId &&
                    !msg.content &&
                    !msg.reasoningContent &&
                    !msg.reasoningBlocks?.length &&
                    !msg.toolData?.length && (
                      <div className={styles.typingIndicator}>
                        <span />
                        <span />
                        <span />
                      </div>
                    )}
                </>
              )}
            </div>
          ))
        )}

        {interruptPanel}

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
              useKnowledgeBase
                ? chatDisabled
                  ? '请先在知识管理中选择一个知识库...'
                  : '输入您的知识库问题...'
                : '输入您的问题...'
            }
            rows={1}
          />
          <div className={styles.toggles}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={useKnowledgeBase}
                onChange={(event) => onKnowledgeBaseToggle(event.target.checked)}
              />
              <span className={styles.toggleSlider} />
              <span className={styles.toggleLabel}>知识库</span>
            </label>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={internetSearch}
                onChange={(event) => onInternetSearchChange(event.target.checked)}
              />
              <span className={styles.toggleSlider} />
              <span className={styles.toggleLabel}>联网</span>
            </label>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={deepThinking}
                onChange={(event) => onDeepThinkingChange(event.target.checked)}
              />
              <span className={styles.toggleSlider} />
              <span className={styles.toggleLabel}>思考</span>
            </label>
          </div>
          {useKnowledgeBase && (
            <div className={styles.chatKnowledgeRow}>
              <span className={styles.chatKnowledgeStatus}>
                {selectedKnowledgeBaseName
                  ? `当前知识库：${selectedKnowledgeBaseName}`
                  : '已开启知识库问答，请先选择知识库'}
              </span>
              <button className={styles.chatKnowledgeAction} onClick={onNavigateToKnowledge}>
                {selectedKnowledgeBaseName ? '切换知识库' : '选择知识库'}
              </button>
            </div>
          )}
        </div>
        {isProcessing ? (
          <button className={styles.abortBtn} onClick={onAbortRequest}>
            中断
          </button>
        ) : (
          <button
            className={styles.sendBtn}
            onClick={() => void onSendMessage()}
            disabled={!inputValue.trim() || chatDisabled}
          >
            发送
          </button>
        )}
      </div>
    </>
  )
}
