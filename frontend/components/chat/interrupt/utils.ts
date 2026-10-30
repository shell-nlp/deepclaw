import type { InterruptData } from '../utils/types'

export type InterruptDecision = 'approve' | 'reject' | 'edit'
type InterruptActionRequest = InterruptData['action_requests'][number]
export type InterruptEditedAction = { name: string; args: Record<string, unknown> }
export type InterruptArgPath = Array<string | number>

export interface AskUserArgs {
  question: string
  header?: string
  options?: Array<{ label: string; description?: string }>
  multiple?: boolean
  custom?: boolean
}

/**
 * 解析人工提问的内容与选项。
 *
 * Args:
 *   interruptData: 当前人工中断数据。
 */
export function getAskUserArgs(interruptData: InterruptData): AskUserArgs | null {
  if (interruptData.action_requests.length !== 1) return null
  const action = interruptData.action_requests[0]
  if (action.name !== 'ask_user') return null
  const args = getInterruptActionArgs(action)
  if (typeof args.question !== 'string') return null

  return {
    question: args.question,
    header: typeof args.header === 'string' ? args.header : undefined,
    options: Array.isArray(args.options)
      ? args.options.flatMap((option) => {
          if (!isRecord(option) || typeof option.label !== 'string') return []
          return [
            {
              label: option.label,
              description:
                typeof option.description === 'string' ? option.description : undefined,
            },
          ]
        })
      : undefined,
    multiple: args.multiple === true,
    custom: args.custom !== false,
  }
}

/**
 * 读取审批请求参数并兼容旧字段。
 *
 * Args:
 *   action: 当前工具审批请求。
 */
export function getInterruptActionArgs(
  action: InterruptActionRequest
): Record<string, unknown> {
  return action.args ?? action.arguments ?? {}
}

/**
 * 判断参数是否为普通对象。
 *
 * Args:
 *   value: 待判断的数据。
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 复制参数对象用于编辑草稿。
 *
 * Args:
 *   value: 待复制的参数。
 */
export function cloneInterruptArgs(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
}

/**
 * 按字段路径更新嵌套参数。
 *
 * Args:
 *   value: 原始参数。
 *   path: 待修改字段的路径。
 *   nextValue: 新的字段值。
 */
export function updateValueAtPath(
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

/**
 * 生成参数字段的展示名称。
 *
 * Args:
 *   key: 字段名称或数组下标。
 */
export function formatArgLabel(key: string | number): string {
  return typeof key === 'number' ? `#${key + 1}` : key
}

/**
 * 校验单个请求是否允许指定审批操作。
 *
 * Args:
 *   interruptData: 当前人工中断数据。
 *   actionIndex: 请求下标。
 *   decision: 待校验的审批操作。
 */
export function isInterruptDecisionAllowed(
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

/**
 * 校验所有请求是否都允许指定审批操作。
 *
 * Args:
 *   interruptData: 当前人工中断数据。
 *   decision: 待校验的审批操作。
 */
export function isDecisionAllowedForAllActions(
  interruptData: InterruptData,
  decision: InterruptDecision
): boolean {
  const actionCount = interruptData?.action_requests?.length || 0
  if (actionCount === 0) return false

  return interruptData.action_requests.every((_, index) =>
    isInterruptDecisionAllowed(interruptData, index, decision)
  )
}

