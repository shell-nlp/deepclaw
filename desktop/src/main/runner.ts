import WebSocket from 'ws'
import type { DesktopState, ExecuteTask, Policy, TaskEvent } from '../shared/protocol'
import { Journal, terminal } from './journal'
import { assertPermission, requiresApproval, serverUrl } from './permissions'
import { isApprovalMode } from '../shared/approval'
import { execute } from './executor'

export interface Credentials { server: string; device_id: string; token: string; name: string }

/** 维护设备连接和本机最终权限；Args: journal 持久化记录, changed 状态推送。 */
export class Runner {
  policy: Policy
  credentials: Credentials | null = null
  connected = false
  error = ''
  private socket: WebSocket | null = null
  private reconnect: ReturnType<typeof setTimeout> | null = null
  private heartbeat: ReturnType<typeof setInterval> | null = null
  private controllers = new Map<string, AbortController>()
  private working = false
  private closed = false
  private retry = 0
  private eventSent = new Set<string>()

  constructor(readonly journal: Journal, private changed: () => void) { this.policy = journal.boot() }

  /** 提供不含凭据的界面快照；Args: 无。 */
  state(): DesktopState { return { server: this.credentials?.server ?? '', name: this.credentials?.name ?? '', paired: !!this.credentials, connected: this.connected, policy: this.policy, tasks: this.journal.tasks(), error: this.error } }

  /** 使用设备专用凭据建立连接；Args: credentials 已配对凭据。 */
  start(credentials: Credentials) {
    this.credentials = { ...credentials, server: serverUrl(credentials.server) }; this.closed = false
    this.connect()
  }

  /** 建立带认证头的 WSS，仅循环重连同一设备；Args: 无。 */
  private connect() {
    if (this.closed || !this.credentials) return
    if (this.socket) this.socket.removeAllListeners()
    const endpoint = new URL('/api/devices/connect', this.credentials.server)
    endpoint.protocol = endpoint.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = this.socket = new WebSocket(endpoint, { headers: { Authorization: `Bearer ${this.credentials.token}` }, maxPayload: 2097152, handshakeTimeout: 10000 })
    socket.on('message', data => {
      try { this.receive(JSON.parse(data.toString())) }
      catch { this.error = '连接协议错误，请检查客户端与服务端版本'; socket.close() }
    })
    socket.on('error', () => { this.error = '连接失败，请检查服务器地址和网络'; this.changed() })
    socket.on('close', code => {
      if (this.heartbeat) clearInterval(this.heartbeat)
      this.connected = false; this.eventSent.clear()
      // 连接丢失先停止本机执行，重连不重放命令。
      this.updatePolicy({ enabled: false })
      if (code === 4401) { this.error = '设备已解绑，请重新配对'; this.closed = true }
      else this.error = '连接已断开，本机访问已关闭'
      this.changed()
      if (!this.closed) this.reconnect = setTimeout(() => this.connect(), Math.min(30000, 1000 * 2 ** Math.min(this.retry++, 5)))
    })
  }

  /** 分发经过结构校验的协议消息；Args: message 服务端数据。 */
  private receive(message: Record<string, unknown>) {
    if (message.type === 'welcome') {
      this.connected = true; this.retry = 0; this.error = ''
      this.policy.revision = Math.max(this.policy.revision, Number(message.revision) || 0) + 1
      this.journal.set('policy', this.policy)
      this.sendPolicy(); this.flush()
      this.heartbeat = setInterval(() => { this.send({ type: 'ping' }); this.flush() }, 10000)
      this.changed()
    } else if (message.type === 'execute') {
      if (typeof message.task_id !== 'string' || !/^[a-f0-9]{64}$/.test(message.task_id) || typeof message.revision !== 'number' || typeof message.expires_at !== 'number' || !message.arguments || typeof message.arguments !== 'object' || Array.isArray(message.arguments)) throw new Error('任务格式不合法')
      this.accept(message as unknown as ExecuteTask)
    } else if (message.type === 'cancel' && typeof message.task_id === 'string') {
      // 尚未收到 execute 的取消也必须持久化，防止后续迟到任务开始执行。
      if (!this.journal.task(message.task_id)) {
        if (!/^[a-f0-9]{64}$/.test(message.task_id) || typeof message.revision !== 'number' || typeof message.expires_at !== 'number' || !message.arguments || typeof message.arguments !== 'object') throw new Error('取消任务格式不合法')
        this.journal.insert({ ...message, type: 'execute' } as unknown as ExecuteTask)
      }
      this.cancel(message.task_id)
    } else if (message.type === 'event_ack' && typeof message.task_id === 'string' && typeof message.sequence === 'number') {
      this.journal.ack(message.task_id, message.sequence)
      for (const key of this.eventSent) if (key.startsWith(`${message.task_id}:`) && Number(key.split(':')[1]) <= message.sequence) this.eventSent.delete(key)
      this.flush()
    }
  }

  /** 变更权限先落本机并中止旧任务，再通知服务端；Args: change 授权变更。 */
  updatePolicy(change: Partial<Policy>) {
    if (change.approvalMode !== undefined && !isApprovalMode(change.approvalMode)) throw new Error('审批模式不合法')
    const old = this.policy
    this.policy = { ...old, ...change, revision: old.revision + 1 }
    if (this.policy.enabled && (!this.connected || !this.policy.roots.length)) { this.policy.enabled = false; this.error = '请先连接服务器并选择授权目录' }
    this.journal.set('policy', this.policy)
    for (const task of this.journal.active()) this.cancel(task.task_id)
    this.sendPolicy(); this.changed()
  }

  /** 发布当前完整权限快照；Args: 无。 */
  private sendPolicy() {
    const { enabled, revision, capabilities, roots } = this.policy
    if (this.connected) this.send({ type: 'policy', enabled, revision, capabilities, roots })
  }

  /** 先持久化接收记录，再决定是否进入本机确认；Args: task 原始任务。 */
  private accept(task: ExecuteTask) {
    const automatic = !requiresApproval(task.operation, this.policy.approvalMode)
    if (!this.journal.insert(task, automatic)) { this.flush(); return }
    try { assertPermission(task, this.policy) }
    catch (error) { this.record(task.task_id, 'rejected', '', { message: (error as Error).message }); return }
    this.record(task.task_id, automatic ? 'queued' : 'awaiting_approval')
    if (!this.working && automatic) void this.decide(task.task_id, true)
  }

  /** 对不可变任务作出本机审批；Args: id 任务标识, approve 是否批准。 */
  async decide(id: string, approve: boolean) {
    const task = this.journal.task(id)
    if (!task || !['awaiting_approval', 'queued'].includes(task.status)) return
    if (!approve) { this.record(id, 'rejected', '', { message: '用户在本机拒绝了此操作' }); return }
    if (this.working) throw new Error('请等待当前任务结束后再批准')
    try { assertPermission(task, this.policy) }
    catch (error) { this.record(id, 'rejected', '', { message: (error as Error).message }); return }
    this.working = true
    const controller = new AbortController(); this.controllers.set(id, controller)
    this.record(id, 'running')
    let buffer = ''
    const flushOutput = () => { if (buffer) { const chunk = buffer; buffer = ''; this.record(id, 'running', chunk) } }
    const timer = setInterval(flushOutput, 150)
    try {
      const result = await execute(task, () => this.policy, controller.signal, text => {
        buffer += text
        while (buffer.length > 8000) { const chunk = buffer.slice(0, 8000); buffer = buffer.slice(8000); this.record(id, 'running', chunk) }
      })
      flushOutput()
      this.record(id, controller.signal.aborted ? 'cancelled' : result.exit_code !== undefined && result.exit_code !== 0 ? 'failed' : 'succeeded', '', result)
    } catch (error) {
      flushOutput()
      this.record(id, controller.signal.aborted ? 'cancelled' : 'failed', '', { message: (error as Error).message })
    } finally {
      clearInterval(timer); this.controllers.delete(id); this.working = false; this.changed()
      // 自动任务按到达顺序继续；权限变更会先取消旧版本任务。
      const next = this.journal.active().find(item => item.status === 'queued')
      if (next) void this.decide(next.task_id, true)
    }
  }

  /** 取消任务，运行中等待实际退出再报告；Args: id 任务标识。 */
  cancel(id: string) {
    const task = this.journal.task(id)
    if (!task || terminal.has(task.status)) return
    const controller = this.controllers.get(id)
    if (controller) controller.abort()
    else this.record(id, 'cancelled', '', { message: '任务已取消，未执行' })
  }

  /** 先持久化事件再发送，断线可重传；Args: id 任务, status 状态, output 新输出, result 最终结果。 */
  private record(id: string, status: TaskEvent['status'], output = '', result: Record<string, unknown> | null = null) {
    this.journal.event(id, status, output, result); this.flush(); this.changed()
  }

  /** 发送尚未确认的事件；Args: 无。 */
  private flush() {
    if (!this.connected) return
    for (const event of this.journal.pending()) {
      const key = `${event.task_id}:${event.sequence}`
      if (!this.eventSent.has(key)) { this.send(event); this.eventSent.add(key) }
    }
  }

  /** 只通过已建立的连接发送；Args: message 协议数据。 */
  private send(message: unknown) { if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message)) }

  /** 停止连接并取消本机任务；Args: 无。 */
  stop() {
    this.closed = true
    this.updatePolicy({ enabled: false })
    if (this.reconnect) clearTimeout(this.reconnect)
    if (this.heartbeat) clearInterval(this.heartbeat)
    this.socket?.close(); this.connected = false; this.changed()
  }

  /** 退出前等待本机进程实际终止；Args: 无。 */
  async shutdown() {
    this.stop()
    const deadline = Date.now() + 5000
    while ((this.controllers.size || (this.socket && this.socket.readyState !== WebSocket.CLOSED)) && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 25))
    if (this.socket?.readyState !== WebSocket.CLOSED) this.socket?.terminate()
  }
}
