import { DatabaseSync } from 'node:sqlite'
import type { ExecuteTask, LocalTask, Policy, TaskEvent, TaskStatus } from '../shared/protocol'
import { isApprovalMode } from '../shared/approval'

export const terminal = new Set<TaskStatus>(['succeeded', 'failed', 'cancelled', 'rejected', 'uncertain'])

/** 持久化任务与未确认事件；Args: filename 数据库位置。 */
export class Journal {
  private db: DatabaseSync
  constructor(filename: string) {
    this.db = new DatabaseSync(filename)
    this.db.exec('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL, seq INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS events (task_id TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(task_id,seq));')
  }
  /** 读取本机设置；Args: key 配置键, fallback 默认值。 */
  get<T>(key: string, fallback: T): T { const row = this.db.prepare('SELECT value FROM settings WHERE key=?').get(key); return row ? JSON.parse(String(row.value)) as T : fallback }
  /** 保存本机设置；Args: key 配置键, value 配置值。 */
  set(key: string, value: unknown) { this.db.prepare('INSERT OR REPLACE INTO settings VALUES (?,?)').run(key, JSON.stringify(value)) }
  /** 获取本机任务；Args: id 稳定任务标识。 */
  task(id: string): LocalTask | undefined { const row = this.db.prepare('SELECT body FROM tasks WHERE id=?').get(id); return row ? JSON.parse(String(row.body)) : undefined }
  /** 获取最近任务；Args: 无。 */
  tasks(): LocalTask[] { return this.db.prepare('SELECT body FROM tasks ORDER BY rowid DESC LIMIT 50').all().map(row => JSON.parse(String(row.body))) }
  /** 获取所有未结束任务，不受界面分页影响；Args: 无。 */
  active(): LocalTask[] { return this.db.prepare('SELECT body FROM tasks ORDER BY rowid').all().map(row => JSON.parse(String(row.body)) as LocalTask).filter(task => !terminal.has(task.status)) }
  /** 先登记再审批，同一 ID 永远不能二次启动；Args: task 服务端任务, automatic 是否由本机策略自动批准。 */
  insert(task: ExecuteTask, automatic = false): boolean { return this.db.prepare('INSERT OR IGNORE INTO tasks(id,body) VALUES (?,?)').run(task.task_id, JSON.stringify({ ...task, status: automatic ? 'queued' : 'awaiting_approval', approval: automatic ? 'automatic' : 'manual', output: '', result: null })).changes > 0 }
  /** 原子记录状态及待确认事件；Args: id 任务, status 状态, output 新增输出, result 结果。 */
  event(id: string, status: TaskStatus, output = '', result: Record<string, unknown> | null = null): TaskEvent {
    const task = this.task(id)
    if (!task) throw new Error('任务不存在')
    this.db.exec('BEGIN IMMEDIATE')
    try {
      const row = this.db.prepare('SELECT seq FROM tasks WHERE id=?').get(id)!
      const sequence = Number(row.seq) + 1
      const event: TaskEvent = { type: 'task_event', task_id: id, sequence, status, output, result }
      this.db.prepare('UPDATE tasks SET seq=?,body=? WHERE id=?').run(sequence, JSON.stringify({ ...task, status, output: (task.output + output).slice(-131072), result }), id)
      this.db.prepare('INSERT INTO events VALUES (?,?,?)').run(id, sequence, JSON.stringify(event))
      this.db.exec('COMMIT')
      return event
    } catch (error) { this.db.exec('ROLLBACK'); throw error }
  }
  /** 读取未确认事件；Args: 无。 */
  pending(): TaskEvent[] { return this.db.prepare('SELECT body FROM events ORDER BY rowid LIMIT 256').all().map(row => JSON.parse(String(row.body))) }
  /** 服务器确认后清理事件；Args: id 任务, sequence 已确认序号。 */
  ack(id: string, sequence: number) { this.db.prepare('DELETE FROM events WHERE task_id=? AND seq<=?').run(id, sequence) }
  /** 每次启动关闭权限，并隔离重启前的任务；Args: 无。 */
  boot(): Policy {
    const policy = this.get<Policy>('policy', { enabled: false, revision: 0, capabilities: ['files.read'], roots: [], approvalMode: 'confirm' })
    policy.approvalMode = isApprovalMode(policy.approvalMode) ? policy.approvalMode : 'confirm'
    policy.enabled = false; policy.revision += 1; this.set('policy', policy)
    for (const task of this.active()) this.event(task.task_id, task.status === 'running' ? 'uncertain' : 'cancelled', '', { message: '客户端已重启，未重新执行，请核对已有操作结果' })
    return policy
  }
  /** 关闭数据库连接；Args: 无。 */
  close() { this.db.close() }
}
