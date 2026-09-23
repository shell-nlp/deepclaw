import type { TokenUsage } from './types'

export type AgUiEvent = {
  type: string
  [key: string]: unknown
}

export type AgUiInterrupt = {
  interrupt_id?: string
  action_requests?: Array<{
    name: string
    description?: string
    args?: Record<string, unknown>
    arguments?: Record<string, unknown>
  }>
  review_configs?: Array<{
    action_name: string
    allowed_decisions: Array<'approve' | 'edit' | 'reject' | 'respond'>
    args_schema?: Record<string, unknown>
  }>
  [key: string]: unknown
}

export type AgUiResumeEntry = {
  interruptId: string
  status: 'resolved' | 'cancelled'
  payload?: unknown
}

export type AgUiRunInput = {
  agentId: string
  threadId: string
  runId: string
  state: Record<string, unknown>
  messages: Array<{ id: string; role: 'user'; content: string }>
  tools: unknown[]
  context: unknown[]
  forwardedProps: Record<string, unknown>
  resume?: AgUiResumeEntry[]
}

export type AgUiSseFrame = {
  id?: string
  event: AgUiEvent
}

export function createAgUiRunInput(input: {
  agentId: string
  threadId: string
  runId: string
  messageId: string
  query: string
  state: Record<string, unknown>
  forwardedProps?: Record<string, unknown>
}): AgUiRunInput {
  return {
    agentId: input.agentId,
    threadId: input.threadId,
    runId: input.runId,
    state: input.state,
    messages: [{ id: input.messageId, role: 'user', content: input.query }],
    tools: [],
    context: [],
    forwardedProps: input.forwardedProps ?? {},
  }
}

export function parseAgUiSseFrame(frame: string): AgUiSseFrame | null {
  let id: string | undefined
  const dataLines: string[] = []

  for (const rawLine of frame.replace(/\r\n/g, '\n').split('\n')) {
    const line = rawLine.trimEnd()
    if (line.startsWith('id:')) {
      id = line.slice(3).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (dataLines.length === 0) return null
  const raw = dataLines.join('\n')
  if (!raw || raw === '[DONE]') return null

  try {
    const event = JSON.parse(raw) as AgUiEvent
    if (!event || typeof event.type !== 'string') return null
    return { id, event }
  } catch {
    return null
  }
}

export function getAgUiInterrupt(event: AgUiEvent): AgUiInterrupt | null {
  if (event.type !== 'CUSTOM' || event.name !== 'on_interrupt') return null
  return normalizeInterruptValue(parseAgUiValue(event.value))
}

export function getAgUiInterruptOutcome(event: AgUiEvent): AgUiInterrupt | null {
  if (event.type !== 'RUN_FINISHED') return null
  const outcome = asRecord(event.outcome)
  if (!outcome || outcome.type !== 'interrupt') return null
  const interrupts = Array.isArray(outcome.interrupts) ? outcome.interrupts : []

  for (const rawInterrupt of interrupts) {
    const interrupt = asRecord(rawInterrupt)
    if (!interrupt) continue
    const metadata = asRecord(interrupt.metadata)
    const langgraph = asRecord(metadata?.langgraph)
    const rawValue = parseAgUiValue(langgraph?.raw ?? interrupt.message)
    const normalized = normalizeInterruptValue(rawValue)
    if (!normalized) continue
    return {
      ...normalized,
      interrupt_id:
        typeof interrupt.id === 'string' ? interrupt.id : undefined,
    }
  }

  return null
}

function normalizeInterruptValue(value: unknown): AgUiInterrupt | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  if (Array.isArray(record.action_requests)) {
    return record as AgUiInterrupt
  }

  if (typeof record.question === 'string') {
    return {
      action_requests: [
        {
          name: 'ask_user',
          description: record.question,
          args: record,
        },
      ],
      review_configs: [
        {
          action_name: 'ask_user',
          allowed_decisions: ['respond'],
        },
      ],
    }
  }

  return null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function parseAgUiValue(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value) as unknown
  } catch {
    return null
  }
}

export function getRecommendedQuestions(event: AgUiEvent): string[] {
  if (event.type !== 'CUSTOM') return []
  const value = event.value
  const candidate =
    Array.isArray(value)
      ? value
      : value && typeof value === 'object' && 'recommended_questions' in value
        ? (value as Record<string, unknown>).recommended_questions
        : null
  if (!Array.isArray(candidate)) return []
  return candidate
    .filter((question): question is string => typeof question === 'string' && question.trim().length > 0)
    .map((question) => question.trim())
}

export function getAgUiAssistantSnapshotText(event: AgUiEvent): string | null {
  if (event.type !== 'MESSAGES_SNAPSHOT') return null
  const messages = event.messages
  if (!Array.isArray(messages)) return null
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (!message || typeof message !== 'object') continue
    const record = message as Record<string, unknown>
    if (record.role !== 'assistant') continue
    const content = record.content
    if (typeof content === 'string' && content.length > 0) return content
    if (Array.isArray(content)) {
      const text = content
        .map((block) =>
          block && typeof block === 'object' && typeof (block as Record<string, unknown>).text === 'string'
            ? String((block as Record<string, unknown>).text)
            : ''
        )
        .join('')
      if (text.length > 0) return text
    }
  }
  return null
}

function readTokenCount(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
}

function tokenUsageFromRecord(record: Record<string, unknown>): TokenUsage | null {
  const inputTokens =
    readTokenCount(record.input_tokens) ||
    readTokenCount(record.inputTokens) ||
    readTokenCount(record.prompt_tokens) ||
    readTokenCount(record.promptTokens)
  const outputTokens =
    readTokenCount(record.output_tokens) ||
    readTokenCount(record.outputTokens) ||
    readTokenCount(record.completion_tokens) ||
    readTokenCount(record.completionTokens)
  const totalTokens =
    readTokenCount(record.total_tokens) ||
    readTokenCount(record.totalTokens) ||
    inputTokens + outputTokens

  if (inputTokens <= 0 && outputTokens <= 0 && totalTokens <= 0) return null
  return { inputTokens, outputTokens, totalTokens }
}

export function addTokenUsage(
  current: TokenUsage | undefined,
  next: TokenUsage
): TokenUsage {
  return {
    inputTokens: (current?.inputTokens || 0) + next.inputTokens,
    outputTokens: (current?.outputTokens || 0) + next.outputTokens,
    totalTokens: (current?.totalTokens || 0) + next.totalTokens,
  }
}

export function getTokenUsageFromMessage(
  message: Record<string, unknown>
): TokenUsage | null {
  const directUsage = message.usage_metadata || message.usageMetadata
  if (directUsage && typeof directUsage === 'object' && !Array.isArray(directUsage)) {
    const usage = tokenUsageFromRecord(directUsage as Record<string, unknown>)
    if (usage) return usage
  }

  const responseMetadata = message.response_metadata
  if (
    responseMetadata &&
    typeof responseMetadata === 'object' &&
    !Array.isArray(responseMetadata)
  ) {
    const tokenUsage = (responseMetadata as Record<string, unknown>).token_usage
    if (tokenUsage && typeof tokenUsage === 'object' && !Array.isArray(tokenUsage)) {
      const usage = tokenUsageFromRecord(tokenUsage as Record<string, unknown>)
      if (usage) return usage
    }
  }

  return null
}

export function getLatestAssistantTurnTokenUsage(
  messages: unknown
): TokenUsage | null {
  if (!Array.isArray(messages)) return null
  let usage: TokenUsage | null = null

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (!message || typeof message !== 'object' || Array.isArray(message)) continue
    const record = message as Record<string, unknown>
    const type = String(record.type || record.role || '').toLowerCase()
    if (type === 'human' || type === 'user') break
    if (type !== 'ai' && type !== 'assistant') continue
    const messageUsage = getTokenUsageFromMessage(record)
    if (messageUsage) {
      usage = addTokenUsage(usage || undefined, messageUsage)
    }
  }

  return usage
}
