'use client'

import { useEffect, useState } from 'react'
import type { ActorState } from '../utils/auth'
import type { useDevices, DeviceRequest, ClientDeviceTask } from '../hooks/useDevices'
import { DeviceDetail } from './devices/DeviceDetail'
import { DeviceTaskList } from './devices/DeviceTaskList'
import { DeviceDownload } from './devices/DeviceDownload'
import { DeviceConnectionPanel } from './devices/DeviceConnectionPanel'
import { useDeviceInstaller } from '../hooks/useDeviceInstaller'
import styles from './devices/Devices.module.css'

/** 编排设备管理、配对和执行记录；Args: actor 当前用户, state 设备状态, requestJson 鉴权请求, onLogin 登录入口。 */
export function DeviceManagementView({ actor, state, requestJson, onLogin }: { actor: ActorState; state: ReturnType<typeof useDevices>; requestJson: DeviceRequest; onLogin: () => void }) {
  const [activeId, setActiveId] = useState('')
  const { installer, retry } = useDeviceInstaller()
  const [pairing, setPairing] = useState<{ code: string; expires_at: number } | null>(null)
  const [now, setNow] = useState(Date.now())
  const [tasks, setTasks] = useState<ClientDeviceTask[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [revision, setRevision] = useState(0)
  const device = state.devices.find(item => item.id === activeId) || state.devices[0]
  const deviceId = device?.id
  const ownerId = actor.userId
  useEffect(() => { setPairing(null); setTasks([]); setActiveId(''); setError('') }, [ownerId])
  useEffect(() => {
    if (!pairing) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [pairing])
  useEffect(() => {
    setTasks([])
    if (!deviceId) return
    const controller = new AbortController()
    let loading = false
    /** 刷新当前设备任务，忽略已卸载和过期响应；Args: 无。 */
    async function load() {
      if (loading) return
      loading = true
      try { const result = await requestJson<{ items: ClientDeviceTask[] }>(`/api/devices/${deviceId}/tasks`, { signal: controller.signal }); if (!controller.signal.aborted) setTasks(result.items) }
      catch { if (!controller.signal.aborted) setError('执行记录加载失败，请刷新重试。') }
      finally { loading = false }
    }
    void load(); const timer = window.setInterval(() => void load(), 3000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [deviceId, requestJson, revision])
  /** 提交设备管理操作并刷新相关状态；Args: key 操作标识, action 请求动作。 */
  async function act(key: string, action: () => Promise<void>) {
    if (busy) return
    setBusy(key); setError('')
    try { await action(); state.refresh(); setRevision(value => value + 1) }
    catch { setError('操作失败，请检查登录状态后重试。') }
    finally { setBusy('') }
  }
  const remaining = pairing ? Math.max(0, Math.ceil((pairing.expires_at * 1000 - now) / 1000)) : 0
  return <div className={styles.page}><header className={styles.header}><div><h1>我的设备</h1><p>把工作交给智能体，把本机控制权留在自己手里。</p></div><div className={styles.headerActions}>{(actor.isGuest || state.devices.length > 0) && <DeviceDownload installer={installer} onRetry={retry}/>}<div>{!actor.isGuest && <button className={styles.primary} disabled={!!busy} onClick={() => void act('pair', async () => { setPairing(await requestJson('/api/devices/pairings', { method: 'POST' })); setNow(Date.now()) })}>连接新设备</button>}</div></div></header>
    {(error || state.error) && <div className={styles.error} role="alert">{error || state.error}<button onClick={state.refresh}>刷新</button></div>}
    {actor.isGuest ? <div className={styles.empty}><DeviceOutline/><h2>登录后，连接你的电脑</h2><p>设备只归属于你的账户。每台电脑独立授权，随时关闭。</p><button className={styles.primary} onClick={onLogin}>前往登录</button></div> : <>
      <DeviceConnectionPanel code={pairing?.code} remaining={remaining} onCollapse={() => setPairing(null)}/>
      {!state.devices.length ? <div className={styles.empty}><DeviceOutline/><h2>{state.loading ? '正在查询设备…' : '连接第一台电脑'}</h2><p>安装并打开 DeepClaw 本机助手，然后点击「连接新设备」生成配对码。</p><DeviceDownload installer={installer} onRetry={retry}/><div className={styles.steps}><span>下载安装</span><b>›</b><span>配对账户</span><b>›</b><span>在本机开启访问</span></div></div> : <div className={styles.layout}><nav className={styles.deviceList} aria-label="我的设备列表">{state.devices.map(item => <button key={item.id} aria-current={deviceId === item.id ? 'true' : undefined} onClick={() => setActiveId(item.id)}><DeviceOutline/><span><strong>{item.name}</strong><small>{item.enabled ? '允许访问' : item.online ? '访问已关闭' : '离线'}</small></span><i data-online={item.online}/></button>)}</nav><div className={styles.content}>{device && <DeviceDetail key={device.id} device={device} busy={!!busy} onRevoke={() => void act('revoke', () => requestJson(`/api/devices/${device.id}`, { method: 'DELETE' }))}/>}<DeviceTaskList tasks={tasks} busy={busy} onCancel={id => void act(id, () => requestJson(`/api/devices/${deviceId}/tasks/${id}/cancel`, { method: 'POST' }))}/></div></div>}
    </>}
  </div>
}

/** 绘制设备管理中的电脑标识；Args: 无。 */
function DeviceOutline() { return <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="4" y="5" width="24" height="17" rx="2"/><path d="M11 27h10M16 22v5M8 18h16"/></svg> }
