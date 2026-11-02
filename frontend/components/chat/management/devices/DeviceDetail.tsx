import { useState } from 'react'
import type { ClientDevice } from '../../hooks/useDevices'
import styles from './Devices.module.css'

/** 展示本机授权状态，网页不提供开启本机权限的入口；Args: device 设备, busy 提交状态, onRevoke 解绑回调。 */
export function DeviceDetail({ device, busy, onRevoke }: { device: ClientDevice; busy: boolean; onRevoke: () => void }) {
  const [confirming, setConfirming] = useState(false)
  return <section className={styles.detail}><div className={styles.deviceHeading}><div><h2>{device.name}</h2><p>{device.platform === 'win32' ? 'Windows' : device.platform === 'darwin' ? 'macOS' : device.platform}</p></div><span className={styles.status} data-enabled={device.enabled}>{device.enabled ? '允许访问' : device.online ? '访问已关闭' : '设备离线'}</span></div>
    <div className={styles.accessStatement}><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m16 3 11 4v9c0 7-11 13-11 13S5 23 5 16V7z"/><path d="m11 15 4 4 6-8"/></svg><div><strong>{device.enabled ? '在你的授权范围内工作' : '本机访问由这台电脑控制'}</strong><p>{device.enabled ? '智能体仅能使用以下已授权能力。文件写入和命令执行需要本机确认。' : '请在这台电脑的 DeepClaw 本机助手中打开访问开关。网页无法代为开启。'}</p></div></div>
    <div className={styles.permissions}>{[['files.read', '读取文件'], ['files.write', '修改文件'], ['command.run', '运行命令']].map(([capability, label]) => <div key={capability}><span>{label}</span><strong>{device.enabled && device.capabilities.includes(capability) ? '已授权' : '不可用'}</strong></div>)}</div>
    <div className={styles.rootSection}><h3>授权目录</h3>{device.roots.length ? device.roots.map(root => <p key={root} title={root}>{root}</p>) : <p>尚未选择目录，请在本机助手中添加。</p>}</div>
    <div className={styles.revoke}><span>解绑会撤销设备凭据，并请求停止未完成任务。</span>{confirming ? <><button className={styles.dangerButton} disabled={busy} onClick={onRevoke}>确认解绑</button><button className={styles.textButton} onClick={() => setConfirming(false)}>取消</button></> : <button className={styles.textButton} disabled={busy} onClick={() => setConfirming(true)}>解绑设备</button>}</div>
  </section>
}
