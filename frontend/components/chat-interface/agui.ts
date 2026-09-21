export type AgUiEvent = {
  type: string
  [key: string]: unknown
}

export type AgUiInterrupt = {
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

export type AgUiRunInput = {
  agentId: string
  threadId: string
  runId: string
  state: Record<string, unknown>
  messages: Array<{ id: string; role: 'user'; content: string }>
  tools: unknown[]
  context: unknown[]
  forwardedProps: Record<string, unknown>
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
  const value = parseAgUiValue(event.value)
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
