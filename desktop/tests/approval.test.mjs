import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { once } from 'node:events'
import { WebSocketServer } from 'ws'
import { requiresApproval, validatePolicyChange } from '../dist/main/permissions.js'
import { Journal } from '../dist/main/journal.js'
import { Runner } from '../dist/main/runner.js'

/** 等待真实任务状态并限定超时。
 * Args:
 *   check: 状态判断。
 */
async function until(check) {
  const end = Date.now() + 6000
  while (!check()) { if (Date.now() > end) throw new Error('等待任务超时'); await new Promise(resolve => setTimeout(resolve, 15)) }
}

/** 创建隔离数据库、目录和真实回环 WebSocket。
 * Args:
 *   t: 测试上下文。
 *   mode: 本机设置的模式。
 */
async function connectedRunner(t, mode = 'confirm') {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'deepclaw-approval-'))
  const journal = new Journal(path.join(root, 'device.db'))
  const server = new WebSocketServer({ port: 0, host: '127.0.0.1' })
  await once(server, 'listening')
  const runner = new Runner(journal, () => {})
  t.after(async () => {
    await runner.shutdown()
    for (const client of server.clients) client.terminate()
    await new Promise(resolve => server.close(resolve))
    journal.close(); await fs.rm(root, { recursive: true, force: true })
  })
  const connection = once(server, 'connection')
  runner.start({ server: `http://127.0.0.1:${server.address().port}`, device_id: 'test', token: 'test-only', name: '测试电脑' })
  const [socket] = await connection
  socket.send(JSON.stringify({ type: 'welcome', revision: 1 }))
  await until(() => runner.connected)
  runner.updatePolicy({ enabled: true, approvalMode: mode, roots: [root], capabilities: ['files.read', 'files.write', 'command.run'] })
  /** 使用当前授权版本发送任务。
   * Args:
   *   id: 单字符测试标识。
   *   operation: 操作名称。
   *   args: 执行参数。
   *   extra: 用于测试不可信协议字段。
   */
  function send(id, operation, args, extra = {}) {
    const task = { type: 'execute', task_id: id.repeat(64), revision: runner.policy.revision, expires_at: Date.now() / 1000 + 60, operation, arguments: args, ...extra }
    socket.send(JSON.stringify(task))
    return task
  }
  return { root, journal, runner, socket, send }
}

test('两档审批矩阵与本机 IPC 校验：未知模式不获得自动批准', () => {
  for (const mode of ['confirm', 'auto', undefined, 'unknown']) {
    assert.equal(requiresApproval('read_file', mode), false)
    assert.equal(requiresApproval('list_files', mode), false)
    assert.equal(requiresApproval('write_file', mode), mode !== 'auto')
    assert.equal(requiresApproval('run_command', mode), mode !== 'auto')
  }
  assert.deepEqual(validatePolicyChange({ approvalMode: 'auto', allowCommand: false }), { approvalMode: 'auto', allowCommand: false })
  for (const invalid of [null, [], { approvalMode: 'files' }, { approvalMode: true }, { enabled: 'true' }, { roots: ['C:\\'] }]) assert.throws(() => validatePolicyChange(invalid), /不合法/)
})

test('请求批准：服务端伪造自动模式无效，文件和命令不经本机批准不执行', async t => {
  const { root, journal, runner, socket, send } = await connectedRunner(t)
  socket.send(JSON.stringify({ type: 'policy', approvalMode: 'auto', enabled: true }))
  const file = path.join(root, 'manual.txt')
  const write = send('a', 'write_file', { path: file, content: '批准写入' }, { approvalMode: 'auto', approval: 'automatic' })
  const command = send('b', 'run_command', { cwd: root, program: process.execPath, argv: ['-e', 'require("fs").writeFileSync("command.txt","unexpected")'] })
  await until(() => journal.task(command.task_id)?.status === 'awaiting_approval')
  assert.equal(runner.policy.approvalMode, 'confirm')
  assert.equal(journal.task(write.task_id).approval, 'manual')
  await assert.rejects(fs.access(file))
  await runner.decide(write.task_id, true)
  await runner.decide(command.task_id, false)
  assert.equal(await fs.readFile(file, 'utf8'), '批准写入')
  await assert.rejects(fs.access(path.join(root, 'command.txt')))
})

test('完全访问：真实命令与写入按顺序自动执行，同一任务重复投递仍只执行一次', async t => {
  const { root, journal, socket, send } = await connectedRunner(t, 'auto')
  const first = send('a', 'run_command', { cwd: root, program: process.execPath, argv: ['-e', 'setTimeout(()=>{require("fs").appendFileSync("count.txt","1");require("fs").appendFileSync("order.txt","1")},200)'] })
  send('b', 'write_file', { path: path.join(root, 'order.txt'), content: '2' })
  const last = send('c', 'run_command', { cwd: root, program: process.execPath, argv: ['-e', 'require("fs").appendFileSync("order.txt","3")'] })
  socket.send(JSON.stringify(first))
  await until(() => journal.task(last.task_id)?.status === 'succeeded')
  socket.send(JSON.stringify(first))
  assert.equal(await fs.readFile(path.join(root, 'count.txt'), 'utf8'), '1')
  assert.equal(await fs.readFile(path.join(root, 'order.txt'), 'utf8'), '23')
  assert.ok(journal.tasks().every(item => item.approval === 'automatic'))
  assert.equal(journal.pending().some(event => event.status === 'awaiting_approval'), false)
  assert.ok(journal.pending().some(event => event.status === 'queued'))
})

test('完全访问仍校验目录和能力，关闭开关不会被审批模式绕过', async t => {
  const { root, journal, runner, send } = await connectedRunner(t, 'auto')
  const outside = send('a', 'write_file', { path: path.join(root, '..', `${path.basename(root)}-outside.txt`), content: '越界' })
  await until(() => journal.task(outside.task_id)?.status === 'failed')
  assert.match(journal.task(outside.task_id).result.message, /授权目录/)
  runner.updatePolicy({ capabilities: ['files.read'] })
  const denied = send('b', 'write_file', { path: path.join(root, 'denied.txt'), content: '不应写入' })
  await until(() => journal.task(denied.task_id)?.status === 'rejected')
  runner.updatePolicy({ enabled: false })
  const disabled = send('c', 'list_files', { path: root })
  await until(() => journal.task(disabled.task_id)?.status === 'rejected')
  await assert.rejects(fs.access(path.join(root, 'denied.txt')))
})

test('降为请求批准会停止运行进程、取消排队任务，旧任务不能重放', async t => {
  const { root, journal, runner, socket, send } = await connectedRunner(t, 'auto')
  const running = send('a', 'run_command', { cwd: root, program: process.execPath, argv: ['-e', 'process.stdout.write("started");setInterval(()=>{},100)'] })
  await until(() => journal.task(running.task_id)?.output.includes('started'))
  const queued = send('b', 'write_file', { path: path.join(root, 'queued.txt'), content: '不应写入' })
  await until(() => journal.task(queued.task_id)?.status === 'queued')
  runner.updatePolicy({ approvalMode: 'confirm' })
  await until(() => journal.task(running.task_id)?.status === 'cancelled')
  assert.equal(journal.task(queued.task_id).status, 'cancelled')
  socket.send(JSON.stringify(queued))
  const manual = send('c', 'write_file', { path: path.join(root, 'manual.txt'), content: '需要确认' })
  await until(() => journal.task(manual.task_id)?.status === 'awaiting_approval')
  await assert.rejects(fs.access(path.join(root, 'queued.txt')))
  await assert.rejects(fs.access(path.join(root, 'manual.txt')))
})

test('升级旧配置默认请求批准，保存偏好后重启仍关闭总开关', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'deepclaw-policy-'))
  const journal = new Journal(path.join(root, 'device.db'))
  t.after(async () => { journal.close(); await fs.rm(root, { recursive: true, force: true }) })
  journal.set('policy', { enabled: true, revision: 1, roots: [root], capabilities: ['files.read'] })
  assert.equal(journal.boot().approvalMode, 'confirm')
  journal.set('policy', { ...journal.boot(), enabled: true, approvalMode: 'auto' })
  const rebooted = journal.boot()
  assert.equal(rebooted.enabled, false)
  assert.equal(rebooted.approvalMode, 'auto')
  journal.set('policy', { ...rebooted, approvalMode: 'unknown' })
  assert.equal(journal.boot().approvalMode, 'confirm')
})
