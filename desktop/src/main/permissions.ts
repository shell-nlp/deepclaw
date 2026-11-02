import path from 'node:path'
import fs from 'node:fs/promises'
import type { ApprovalMode, ExecuteTask, Operation, Policy, PolicyChange } from '../shared/protocol'
import { isApprovalMode } from '../shared/approval'

const capabilities = { list_files: 'files.read', read_file: 'files.read', write_file: 'files.write', run_command: 'command.run' }

/** 校验来自本机界面的权限修改，禁止未知字段和非法模式。
 * Args:
 *   change: IPC 提交的权限修改。
 */
export function validatePolicyChange(change: unknown): PolicyChange {
  if (!change || typeof change !== 'object' || Array.isArray(change) || Object.entries(change).some(([key, value]) =>
    key === 'approvalMode' ? !isApprovalMode(value) : !['enabled', 'allowWrite', 'allowCommand'].includes(key) || typeof value !== 'boolean')) throw new Error('授权参数不合法')
  return change as PolicyChange
}

/** 根据本机模式判定是否逐次询问，不改变能力和目录校验。
 * Args:
 *   operation: 待执行操作。
 *   mode: 本机保存的审批模式。
 */
export function requiresApproval(operation: Operation, mode: ApprovalMode): boolean {
  if (operation === 'list_files' || operation === 'read_file') return false
  if (operation === 'write_file') return mode !== 'auto'
  return operation !== 'run_command' || mode !== 'auto'
}

/** 校验本机开关、权限版本和任务期限；Args: task 原始任务, policy 本机授权。 */
export function assertPermission(task: ExecuteTask, policy: Policy) {
  if (!policy.enabled || policy.revision !== task.revision) throw new Error('本机访问已关闭或授权已变更')
  if (!Object.hasOwn(capabilities, task.operation) || !policy.capabilities.includes(capabilities[task.operation] as never)) throw new Error('本机未授权此操作')
  if (Date.now() >= task.expires_at * 1000) throw new Error('任务已过期，请重新发起')
}

/** 使用真实路径校验目录边界，阻止路径穿越与链接越界；Args: input 路径, roots 授权目录, writing 是否允许新建文件。 */
export async function authorizedPath(input: unknown, roots: string[], writing = false): Promise<string> {
  if (typeof input !== 'string' || !path.isAbsolute(input) || input.includes('\0')) throw new Error('需要授权目录内的绝对路径')
  const resolved = path.resolve(input)
  let real: string
  try { real = await fs.realpath(resolved) }
  catch (error) {
    if (!writing || (error as NodeJS.ErrnoException).code !== 'ENOENT') throw new Error('路径不存在或不可访问')
    real = path.join(await fs.realpath(path.dirname(resolved)), path.basename(resolved))
  }
  for (const root of roots) {
    const base = await fs.realpath(root)
    const relative = path.relative(base, real)
    if (relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))) return real
  }
  throw new Error('此路径不在已授权目录内')
}

/** 只允许 HTTPS 服务端，本机开发可以使用回环 HTTP；Args: input 服务端地址。 */
export function serverUrl(input: string) {
  const url = new URL(input)
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new Error('请输入不包含路径和凭据的服务器地址')
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw new Error('远程服务器必须使用 HTTPS')
  return url.origin
}
