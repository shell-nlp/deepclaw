import test from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { DesktopUpdates, UPDATE_INTERVAL_MS } from '../dist/main/updates.js'

/** 创建可观察调用次数的更新库替身，默认报告一个新版本。
 * Args:
 *   无。
 */
function engineFixture() {
  const engine = new EventEmitter()
  Object.assign(engine, {
    checks: 0, downloads: 0, installs: 0, feed: null, newest: '0.1.3', failure: '',
    setFeedURL(value) { this.feed = value },
    async checkForUpdates() { this.checks += 1; if (this.failure === 'check') throw new Error('private-path'); if (this.newest) this.emit('update-available', { version: this.newest }); return {} },
    async downloadUpdate() { this.downloads += 1; this.emit('download-progress', { percent: 56.6 }); if (this.failure === 'download') throw new Error('private-path') },
    quitAndInstall() { this.installs += 1 },
  })
  return engine
}

/** 等待 Promise 状态转换，不使用实际定时器。
 * Args:
 *   无。
 */
async function settle() { for (let i = 0; i < 6; i++) await Promise.resolve() }

test('每小时只检查，发现版本和用户退出都不触发下载或安装', async t => {
  t.mock.timers.enable({ apis: ['setInterval'] })
  const engine = engineFixture(), states = []
  const updates = new DesktopUpdates(engine, '0.1.2', true, state => states.push(state), async () => {})
  t.after(() => updates.dispose())
  updates.setServer('https://workspace.example.org')
  await settle()
  assert.equal(engine.checks, 1)
  assert.equal(updates.snapshot().status, 'available')
  assert.equal(engine.feed.url, 'https://workspace.example.org/api/devices/updates/')
  t.mock.timers.tick(UPDATE_INTERVAL_MS - 1); await settle()
  assert.equal(engine.checks, 1)
  t.mock.timers.tick(1); await settle()
  assert.equal(engine.checks, 2)
  assert.equal(engine.downloads, 0)
  assert.equal(engine.installs, 0)
  assert.equal(engine.autoDownload, false)
  assert.equal(engine.autoInstallOnAppQuit, false)
  assert.equal(engine.allowDowngrade, false)
  updates.dispose()
  t.mock.timers.tick(UPDATE_INTERVAL_MS); await settle()
  assert.equal(engine.checks, 2)
})

test('只有点击才下载；下载成功后先停止本机任务，再安装；重复点击无效', async t => {
  const engine = engineFixture(), sequence = [], states = []
  engine.quitAndInstall = () => { sequence.push('install'); engine.installs++ }
  const updates = new DesktopUpdates(engine, '0.1.2', true, state => states.push(state), async () => { sequence.push('shutdown') })
  t.after(() => updates.dispose())
  updates.setServer('http://localhost:7869'); await settle()
  const clicked = updates.install()
  await updates.install()
  assert.equal(updates.busy, true)
  assert.throws(() => updates.setServer(null), /正在更新/)
  await clicked
  assert.equal(engine.downloads, 1)
  assert.equal(engine.installs, 1)
  assert.deepEqual(sequence, ['shutdown', 'install'])
  assert.ok(states.some(state => state.percent === 57))
})

test('下载失败不停止任务、不安装，内部错误不进入界面，检查后可重试', async t => {
  const engine = engineFixture(); engine.failure = 'download'
  let shutdowns = 0
  const updates = new DesktopUpdates(engine, '0.1.2', true, () => {}, async () => { shutdowns++ })
  t.after(() => updates.dispose())
  updates.setServer('https://workspace.example.org'); await settle()
  await updates.install()
  assert.equal(updates.snapshot().status, 'error')
  assert.doesNotMatch(updates.snapshot().message, /private-path/)
  assert.equal(shutdowns, 0)
  assert.equal(engine.installs, 0)
  engine.failure = ''; await updates.check(); await updates.install()
  assert.equal(engine.installs, 1)
})

test('检查失败、未配对和开发环境均不下载；解绑后的旧检查不能恢复提示', async t => {
  const engine = engineFixture()
  const updates = new DesktopUpdates(engine, '0.1.2', true, () => {}, async () => {})
  t.after(() => updates.dispose())
  await updates.check(); await updates.install()
  assert.equal(engine.checks, 0)
  engine.failure = 'check'
  updates.setServer('https://workspace.example.org'); await settle()
  assert.equal(updates.snapshot().status, 'error')
  engine.failure = ''
  updates.setServer(null)
  updates.setServer('https://workspace.example.org')
  updates.setServer(null); await settle()
  assert.equal(updates.snapshot().latestVersion, undefined)
  assert.equal(engine.downloads, 0)
  const dev = new DesktopUpdates(engineFixture(), '0.1.2', false, () => {}, async () => {})
  t.after(() => dev.dispose())
  dev.setServer('http://localhost:7869'); await dev.check(); await dev.install()
  assert.equal(dev.snapshot().status, 'unsupported')
})

test('退出发生在下载期间时，下载完成也不安装', async t => {
  const engine = engineFixture()
  let finish
  engine.downloadUpdate = () => new Promise(resolve => { finish = resolve })
  const updates = new DesktopUpdates(engine, '0.1.2', true, () => {}, async () => { throw new Error('不应停止任务') })
  t.after(() => updates.dispose())
  updates.setServer('https://workspace.example.org'); await settle()
  const clicked = updates.install()
  updates.dispose(); finish(); await clicked
  assert.equal(engine.installs, 0)
})
