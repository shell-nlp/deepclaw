import type { DesktopUpdateState } from '../shared/protocol'
import { serverUrl } from './permissions'

export const UPDATE_INTERVAL_MS = 60 * 60 * 1000

interface UpdaterPort {
  autoDownload: boolean
  autoInstallOnAppQuit: boolean
  allowDowngrade: boolean
  on(event: string, listener: (...args: any[]) => void): unknown
  removeListener(event: string, listener: (...args: any[]) => void): unknown
  setFeedURL(options: { provider: 'generic'; url: string }): void
  checkForUpdates(): Promise<unknown>
  downloadUpdate(): Promise<unknown>
  quitAndInstall(isSilent?: boolean, isForceRunAfter?: boolean): void
}

/** 每小时检查已配对服务器，仅由用户点击触发下载和安装。
 * Args:
 *   engine: 成熟更新库的受限接口。
 *   currentVersion: 当前安装版本。
 *   supported: 是否为已打包的 Windows 应用。
 *   changed: 无敏感信息的界面状态推送。
 *   prepareInstall: 安装前关闭本机访问并等待进程停止。
 */
export class DesktopUpdates {
  private state: DesktopUpdateState
  private server = ''
  private generation = 0
  private checking = false
  private disposed = false
  private timer: ReturnType<typeof setInterval>
  private readonly progress = (value: { percent: number }) => {
    if (this.state.status === 'downloading') this.patch({ percent: Math.max(0, Math.min(100, Math.round(value.percent))) })
  }
  private readonly handleError = () => {
    if (this.state.status === 'installing') this.patch({ status: 'error', message: '安装未完成，请重新检查后重试。' })
  }

  constructor(private engine: UpdaterPort, currentVersion: string, private supported: boolean,
    private changed: (state: DesktopUpdateState) => void, private prepareInstall: () => Promise<void>) {
    this.state = { currentVersion, status: supported ? 'idle' : 'unsupported', message: supported ? '配对服务器后，每小时自动检查更新。' : '开发环境不安装更新，请使用 Windows 安装版。' }
    engine.autoDownload = false
    engine.autoInstallOnAppQuit = false
    engine.allowDowngrade = false
    engine.on('download-progress', this.progress)
    engine.on('error', this.handleError)
    this.timer = setInterval(() => { void this.check() }, UPDATE_INTERVAL_MS)
    this.timer.unref?.()
  }

  /** 返回无凭据的更新状态。
   * Args:
   *   无。
   */
  snapshot(): DesktopUpdateState { return { ...this.state } }

  /** 标记下载或安装中，防止同时解绑或切换更新源。
   * Args:
   *   无。
   */
  get busy(): boolean { return ['downloading', 'installing'].includes(this.state.status) }

  /** 绑定当前配对来源；首次连接立即检查，解绑清除旧提示。
   * Args:
   *   server: 可信配对流程保存的服务器根地址。
   */
  setServer(server: string | null) {
    if (this.busy) throw new Error('正在更新，请完成后再解绑设备')
    const origin = server ? serverUrl(server) : ''
    if (origin === this.server) return
    this.server = origin; this.generation += 1
    this.state = { currentVersion: this.state.currentVersion, status: this.supported ? 'idle' : 'unsupported', message: !this.supported ? '开发环境不安装更新，请使用 Windows 安装版。' : origin ? '等待检查更新。' : '配对服务器后，每小时自动检查更新。' }
    this.changed(this.snapshot())
    if (origin) void this.check()
  }

  /** 检查版本，失败保留现有可安装版本，不下载文件。
   * Args:
   *   无。
   */
  async check(): Promise<void> {
    if (this.disposed || !this.supported || !this.server || this.checking || this.busy) return
    this.checking = true
    const generation = this.generation
    const previous = this.snapshot()
    let available: { version: string } | undefined
    const found = (info: { version: string }) => { available = info }
    this.engine.on('update-available', found)
    this.patch({ status: 'checking', message: '正在检查新版本…' })
    try {
      this.engine.setFeedURL({ provider: 'generic', url: `${this.server}/api/devices/updates/` })
      await this.engine.checkForUpdates()
      if (generation !== this.generation || this.disposed) return
      this.patch({ status: available ? 'available' : 'idle', latestVersion: available?.version, percent: undefined,
        lastCheckedAt: Date.now(), message: available ? '新版本已发布，点击后才会下载和安装。' : '当前已是最新版本，每小时自动检查。' })
    } catch {
      if (generation === this.generation && !this.disposed) this.patch({ status: 'error', latestVersion: previous.latestVersion,
        message: '检查更新失败，请检查网络或联系管理员发布安装包。' })
    } finally {
      this.engine.removeListener('update-available', found)
      this.checking = false
      if (!this.disposed && generation !== this.generation) void this.check()
    }
  }

  /** 用户主动点击后下载，经完整性校验成功才停止任务并安装重启。
   * Args:
   *   无。
   */
  async install(): Promise<void> {
    if (this.disposed || this.busy || this.checking || this.state.status !== 'available') return
    this.patch({ status: 'downloading', percent: 0, message: '正在下载更新，完成后将关闭本机访问并重启助手。' })
    try {
      await this.engine.downloadUpdate()
      if (this.disposed) return
      this.patch({ status: 'installing', percent: 100, message: '正在停止本机任务并安装更新…' })
      await this.prepareInstall()
      if (this.disposed) return
      this.engine.quitAndInstall(false, true)
    } catch {
      if (!this.disposed) this.patch({ status: 'error', percent: undefined, message: '更新未完成，请重新检查后重试。助手不会在退出时自动安装。' })
    }
  }

  /** 推送可展示状态，不暴露下载地址和内部异常。
   * Args:
   *   change: 当前状态变化。
   */
  private patch(change: Partial<DesktopUpdateState>) { this.state = { ...this.state, ...change }; this.changed(this.snapshot()) }

  /** 退出时停止定时器和事件订阅，不触发安装。
   * Args:
   *   无。
   */
  dispose() {
    this.disposed = true; clearInterval(this.timer)
    this.engine.removeListener('download-progress', this.progress)
    this.engine.removeListener('error', this.handleError)
  }
}
