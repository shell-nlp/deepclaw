export const REASONING_LABELS = {
  minimal: '极低',
  low: '低',
  medium: '中',
  high: '高',
  xhigh: '很高',
  max: '最高',
} as const

export type ReasoningEffort = keyof typeof REASONING_LABELS
export type ReasoningChoice = 'off' | 'on' | ReasoningEffort

export interface ChatModelOptions {
  items: { id: string; name: string; reasoning_efforts?: ReasoningEffort[] }[]
  default_id: string | null
}
