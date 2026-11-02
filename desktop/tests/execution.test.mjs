import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { once } from 'node:events'
import { WebSocketServer } from 'ws'
import { authorizedPath, assertPermission, serverUrl } from '../dist/main/permissions.js'
import { execute } from '../dist/main/executor.js'
import { Journal } from '../dist/main/journal.js'
import { Runner } from '../dist/main/runner.js'

const policy = root => ({ enabled: true, revision: 7, roots: [root], capabilities: ['files.read', 'files.write', 'command.run'] })
const task = (operation, args, id = 'a') => ({ type: 'execute', task_id: id.repeat(64), revision: 7, expires_at: Date.now() / 1000 + 60, operation, arguments: args })
/** 创建隔离测试目录；Args: t 测试上下文, cleanup 是否自动清理。 */
async function fixture(t, cleanup = true) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'deepclaw-device-'))
  if (cleanup) t.after(() => fs.rm(root, { recursive: true, force: true }))
  return root
}
/** 等待真实异步状态并限制时长；Args: check 状态判断。 */
async function until(check) {
  const end = Date.now() + 5000
  while (!check()) { if (Date.now() > end) throw new Error('等待状态超时'); await new Promise(resolve => setTimeout(resolve, 15)) }
}

test('路径边界拒绝上层、相似前缀和指向外部的目录链接', async t => {
  const root = await fixture(t), allowed = path.join(root, 'allowed'), outside = path.join(root, 'allowed-extra')
  await fs.mkdir(allowed); await fs.mkdir(outside)
  await fs.writeFile(path.join(allowed, 'ok.txt'), '你好')
  await fs.symlink(outside, path.join(allowed, 'escape'), process.platform === 'win32' ? 'junction' : 'dir')
  assert.equal(await authorizedPath(path.join(allowed, 'ok.txt'), [allowed]), await fs.realpath(path.join(allowed, 'ok.txt')))
  await assert.rejects(authorizedPath(outside, [allowed]), /授权目录/)
  await assert.rejects(authorizedPath(path.join(allowed, 'escape'), [allowed]), /授权目录/)
  await assert.rejects(authorizedPath('../other', [allowed]), /绝对路径/)
  assert.throws(() => assertPermission(task('read_file', {}), { ...policy(root), enabled: false }), /关闭/)
  assert.throws(() => assertPermission(task('read_file', {}), { ...policy(root), revision: 8 }), /变更/)
  assert.throws(() => serverUrl('http://example.com'), /HTTPS/)
  assert.equal(serverUrl('http://127.0.0.1:5011'), 'http://127.0.0.1:5011')
})

test('真实文件读写和进程输出、非零退出码、超时、取消', async t => {
  const root = await fixture(t), file = path.join(root, 'text.txt'), access = () => policy(root)
  await execute(task('write_file', { path: file, content: '本机测试' }), access, new AbortController().signal, () => {})
  assert.equal((await execute(task('read_file', { path: file }), access, new AbortController().signal, () => {})).content, '本机测试')
  let output = ''
  const command = args => task('run_command', { cwd: root, program: process.execPath, argv: ['-e', ...args], timeout: 5 })
  assert.equal((await execute(command(['process.stdout.write("你好");process.exitCode=3']), access, new AbortController().signal, text => { output += text })).exit_code, 3)
  assert.equal(output, '你好')
  const timed = command(['setInterval(()=>{},100)']); timed.arguments.timeout = 1
  await assert.rejects(execute(timed, access, new AbortController().signal, () => {}), /超时/)
  const controller = new AbortController()
  const running = execute(command(['setInterval(()=>{},100)']), access, controller.signal, () => {})
  setTimeout(() => controller.abort(), 100)
  await assert.rejects(running, /停止|aborted/)
  await assert.rejects(execute(task('write_file', { path: file, content: 'x'.repeat(262145) }), access, new AbortController().signal, () => {}), /256 KB/)
})

test('持久化先于执行，重启关闭授权且不重跑，事件确认后清理', async t => {
  const root = await fixture(t), file = path.join(root, 'device.db')
  let journal = new Journal(file)
  journal.set('policy', policy(root)); assert.equal(journal.insert(task('run_command', {})), true)
  assert.equal(journal.insert(task('run_command', {})), false)
  journal.event('a'.repeat(64), 'running', '一次输出')
  journal.close(); journal = new Journal(file)
  assert.equal(journal.boot().enabled, false)
  assert.equal(journal.task('a'.repeat(64)).status, 'uncertain')
  assert.equal(journal.task('a'.repeat(64)).output, '一次输出')
  assert.deepEqual(journal.pending().map(event => event.sequence), [1, 2])
  journal.ack('a'.repeat(64), 2); assert.equal(journal.pending().length, 0)
  journal.close()
})

test('真实 WebSocket：本机批准后执行一次，未知取消不执行，断线关闭', async t => {
  const root = await fixture(t, false), journal = new Journal(path.join(root, 'device.db'))
  const server = new WebSocketServer({ port: 0, host: '127.0.0.1' })
  await once(server, 'listening')
  const runner = new Runner(journal, () => {})
  t.after(async () => { await runner.shutdown(); for (const client of server.clients) client.terminate(); await new Promise(resolve => server.close(resolve)); journal.close(); await fs.rm(root, { recursive: true, force: true }) })
  const connected = once(server, 'connection')
  runner.start({ server: `http://127.0.0.1:${server.address().port}`, token: 'test-only', device_id: 'test', name: 'test' })
  const [socket, request] = await connected
  assert.equal(request.headers.authorization, 'Bearer test-only')
  socket.on('message', data => { const event = JSON.parse(data); if (event.type === 'task_event') socket.send(JSON.stringify({ type: 'event_ack', task_id: event.task_id, sequence: event.sequence })) })
  socket.send(JSON.stringify({ type: 'welcome', revision: 5 }))
  await until(() => runner.connected)
  runner.updatePolicy({ enabled: true, roots: [root], capabilities: policy(root).capabilities })
  const filename = path.join(root, 'once.txt')
  const command = task('run_command', { cwd: root, program: process.execPath, argv: ['-e', 'require("fs").appendFileSync("once.txt","1")'], timeout: 5 })
  command.revision = runner.policy.revision
  socket.send(JSON.stringify(command))
  await until(() => journal.task(command.task_id)?.status === 'awaiting_approval')
  await assert.rejects(fs.access(filename))
  await runner.decide(command.task_id, true)
  socket.send(JSON.stringify(command))
  await new Promise(resolve => setTimeout(resolve, 100))
  assert.equal(await fs.readFile(filename, 'utf8'), '1')
  assert.equal(journal.task(command.task_id).status, 'succeeded')
  const cancelled = { ...command, task_id: 'b'.repeat(64), type: 'cancel' }
  socket.send(JSON.stringify(cancelled))
  await until(() => journal.task(cancelled.task_id)?.status === 'cancelled')
  socket.send(JSON.stringify({ ...cancelled, type: 'execute' }))
  assert.equal(await fs.readFile(filename, 'utf8'), '1')
  socket.close(); await until(() => !runner.connected)
  assert.equal(runner.policy.enabled, false)
})
