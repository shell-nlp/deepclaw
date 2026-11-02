import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, safeStorage, Tray } from 'electron'
import { hostname } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { Journal } from './journal'
import { Runner, type Credentials } from './runner'
import { serverUrl } from './permissions'

let window: BrowserWindow | null = null
let tray: Tray | null = null
let exiting = false
let runner: Runner
let journal: Journal
const page = path.join(__dirname, '../../ui/index.html')
const notified = new Set<string>()
const profile = app.commandLine.getSwitchValue('user-data-dir')
if (profile && path.isAbsolute(profile)) app.setPath('userData', profile)

/** 向可信界面推送无凭据快照；Args: 无。 */
function changed() {
  if (!window || window.isDestroyed()) return
  const state = runner.state()
  window.webContents.send('device:changed', state)
  for (const task of state.tasks) {
    if (task.status !== 'awaiting_approval' || !['write_file', 'run_command'].includes(task.operation) || notified.has(task.task_id)) continue
    notified.add(task.task_id)
    if (Notification.isSupported()) {
      const notice = new Notification({ title: '本机操作等待确认', body: '打开 DeepClaw 本机助手，核对操作参数后批准或拒绝。' })
      notice.on('click', show); notice.show()
    }
  }
}

/** 显示本机控制台；Args: 无。 */
function show() { window?.show(); window?.focus() }

/** 创建隔离的本地界面和最小 IPC 入口；Args: 无。 */
async function start() {
  app.setAppUserModelId('com.deepclaw.assistant')
  journal = new Journal(path.join(app.getPath('userData'), 'device.db'))
  runner = new Runner(journal, changed)
  window = new BrowserWindow({ width: 1050, height: 790, minWidth: 760, minHeight: 620, title: 'DeepClaw 本机助手', backgroundColor: '#f3f5f8', show: false,
    webPreferences: { preload: path.join(__dirname, '../preload/index.js'), contextIsolation: true, nodeIntegration: false, sandbox: true } })
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-navigate', event => event.preventDefault())
  window.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false))
  window.on('close', event => { if (!exiting) { event.preventDefault(); window?.hide() } })
  window.once('ready-to-show', show)
  // 仅本地可信页面可以调用固定能力，禁止远程页面利用 IPC。
  const handle = (channel: string, action: (...args: any[]) => unknown) => {
    ipcMain.handle(channel, async (event, ...args) => {
      if (event.sender !== window?.webContents || event.senderFrame?.url !== pathToFileURL(page).href) throw new Error('非法界面来源')
      try { return await action(...args) } catch (error) { throw new Error((error as Error).message || '操作失败，请重试') }
    })
  }
  handle('device:state', () => ({ ...runner.state(), name: runner.state().name || hostname() }))
  handle('device:pair', async (server: string, code: string, name: string) => {
    if (runner.credentials) throw new Error('请先解绑当前设备')
    if (typeof server !== 'string' || typeof code !== 'string' || typeof name !== 'string' || code.length > 128 || !name.trim() || name.length > 80) throw new Error('请填写服务器地址、配对码和设备名称')
    if (!safeStorage.isEncryptionAvailable()) throw new Error('系统凭据加密不可用，无法安全保存设备凭据')
    const origin = serverUrl(server)
    const response = await fetch(`${origin}/api/devices/pairings/claim`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code.trim(), name: name.trim(), platform: process.platform }), signal: AbortSignal.timeout(15000), redirect: 'error' })
    if (!response.ok) throw new Error('配对失败，配对码可能已过期，请在网页重新生成')
    const data = await response.json() as { device_id: string; token: string }
    if (typeof data.device_id !== 'string' || typeof data.token !== 'string') throw new Error('服务器返回的配对信息不完整')
    const credentials: Credentials = { server: origin, name: name.trim(), ...data }
    journal.set('credentials', safeStorage.encryptString(JSON.stringify(credentials)).toString('base64'))
    runner.start(credentials); changed()
  })
  handle('device:policy', (change: { enabled?: boolean; allowWrite?: boolean; allowCommand?: boolean }) => {
    if (!change || typeof change !== 'object' || Object.entries(change).some(([key, value]) => !['enabled', 'allowWrite', 'allowCommand'].includes(key) || typeof value !== 'boolean')) throw new Error('授权参数不合法')
    const capabilities = new Set(runner.policy.capabilities)
    for (const [key, capability] of [['allowWrite', 'files.write'], ['allowCommand', 'command.run']] as const) {
      if (change[key] === true) capabilities.add(capability)
      if (change[key] === false) capabilities.delete(capability)
    }
    runner.updatePolicy({ ...(change.enabled === undefined ? {} : { enabled: change.enabled }), capabilities: [...capabilities] })
  })
  handle('device:add-root', async () => {
    const result = await dialog.showOpenDialog(window!, { title: '选择允许智能体访问的目录', properties: ['openDirectory'] })
    if (!result.canceled) runner.updatePolicy({ roots: [...new Set([...runner.policy.roots, ...result.filePaths])].slice(0, 32) })
  })
  handle('device:remove-root', (root: string) => { if (typeof root !== 'string') throw new Error('目录参数不合法'); runner.updatePolicy({ roots: runner.policy.roots.filter(value => value !== root) }) })
  handle('device:decide', (id: string, approve: boolean) => {
    if (typeof id !== 'string' || typeof approve !== 'boolean') throw new Error('审批参数不合法')
    void runner.decide(id, approve).catch(error => { runner.error = error.message; changed() })
  })
  handle('device:cancel', (id: string) => { if (typeof id !== 'string') throw new Error('任务参数不合法'); runner.cancel(id) })
  handle('device:unpair', () => { runner.stop(); journal.set('credentials', null); runner.credentials = null; changed() })
  await window.loadFile(page)
  // 托盘图标由应用自身绘制，不引入远程资源。
  const icon = nativeImage.createFromPath(path.join(__dirname, '../../assets/icon.png'))
  tray = new Tray(icon)
  tray.setToolTip('DeepClaw 本机助手')
  tray.setContextMenu(Menu.buildFromTemplate([{ label: '打开本机助手', click: show }, { label: '关闭本机访问', click: () => runner.updatePolicy({ enabled: false }) }, { type: 'separator' }, { label: '退出', click: () => app.quit() }]))
  tray.on('double-click', show)
  const encrypted = journal.get<string | null>('credentials', null)
  if (encrypted) {
    try {
      runner.start(JSON.parse(safeStorage.decryptString(Buffer.from(encrypted, 'base64'))))
    }
    catch { runner.error = '设备凭据无法读取，请重新配对'; changed() }
  }
}

if (!app.requestSingleInstanceLock()) app.quit()
else {
  app.on('second-instance', show)
  app.whenReady().then(start).catch(error => { dialog.showErrorBox('本机助手启动失败', String(error.message)); app.quit() })
  app.on('before-quit', event => {
    if (exiting) return
    event.preventDefault()
    exiting = true
    void (runner?.shutdown() ?? Promise.resolve()).finally(() => { journal?.close(); tray?.destroy(); app.quit() })
  })
  app.on('window-all-closed', () => { /* 托盘应用保持运行，由退出操作结束。 */ })
}
