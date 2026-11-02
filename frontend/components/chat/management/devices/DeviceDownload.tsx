'use client'

import type { DeviceInstallerState } from '../../hooks/useDeviceInstaller'
import { getApiUrl } from '../../utils'
import styles from './Devices.module.css'

/** 展示真实下载链接、平台信息与发布异常；Args: installer 发布状态, onRetry 重新查询。 */
export function DeviceDownload({ installer, onRetry }: { installer: DeviceInstallerState; onRetry: () => void }) {
  const available = installer.status === 'available'
  return <div className={styles.download}>
    {available ? <a className={styles.downloadButton} href={getApiUrl('/api/devices/installer/windows-x64')} download="DeepClaw-Setup-x64.exe"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M10 2v10m-4-4 4 4 4-4M3 12v5h14v-5"/></svg>下载 Windows 本机助手</a> : <button className={styles.downloadButton} disabled>{installer.status === 'loading' ? '正在获取安装包…' : '安装包暂不可用'}</button>}
    <small role="status">{available ? `Windows x64 · ${(installer.sizeBytes / 1024 / 1024).toFixed(1)} MB` : installer.status === 'loading' ? '正在检查此服务器的发布状态' : installer.status === 'unavailable' ? '此服务器尚未发布安装包，请联系管理员。' : '无法获取安装包，请检查网络后重试。'}</small>
    {(installer.status === 'unavailable' || installer.status === 'error') && <button className={styles.textButton} onClick={onRetry}>重新检查</button>}
  </div>
}
