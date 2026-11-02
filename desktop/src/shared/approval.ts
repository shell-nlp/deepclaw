import type { ApprovalMode } from './protocol'

export const APPROVAL_MODES = [
  { value: 'confirm', title: '请求批准', description: '读取自动执行，修改文件和运行命令前询问。' },
  { value: 'auto', title: '完全访问权限', description: '自动执行已开启的文件修改和命令，无需逐次确认。' },
] as const

/** 严格识别本机支持的审批模式，未知值不能启用自动执行。
 * Args:
 *   value: 待校验的模式。
 */
export function isApprovalMode(value: unknown): value is ApprovalMode {
  return APPROVAL_MODES.some(mode => mode.value === value)
}
