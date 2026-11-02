import { useEffect, useState } from 'react'
import type { DesktopUpdateState } from '../../shared/protocol'
import './UpdatePanel.css'

/** 展示版本检查、用户主动更新与下载进度，不自动提交安装。
 * Args:
 *   无。
 */
export function UpdatePanel() {
  const [state, setState] = useState<DesktopUpdateState | null>(null)
  const [error, setError] = useState('')
  const bridge = window.deepclaw
  useEffect(() => {
    if (!bridge?.updateState || !bridge.subscribeUpdate) return
    let active = true
    bridge.updateState().then(value => { if (active) setState(value) }).catch(() => { if (active) setError('版本信息加载失败，请重新打开助手。') })
    const unsubscribe = bridge.subscribeUpdate(value => { if (active) { setState(value); setError('') } })
    return () => { active = false; unsubscribe() }
  }, [bridge])
  /** 调用固定更新操作，错误保留在更新面板。
   * Args:
   *   install: 是否由用户主动要求安装。
   */
  async function act(install: boolean) {
    if (!bridge) return
    setError('')
    try { if (install) await bridge.installUpdate(); else await bridge.checkUpdate() }
    catch { setError('更新操作未完成，请重新检查后重试。') }
  }
  if (!state && !error) return null
  const busy = state && ['checking', 'downloading', 'installing'].includes(state.status)
  return <section className="update-panel" data-available={state?.status === 'available'} aria-label="助手版本更新">
    <div className="update-heading"><div><h3>{state?.latestVersion && state.status === 'available' ? `新版本 ${state.latestVersion} 已发布` : '助手更新'}</h3><p>{error || state?.message}</p></div><span className="update-version">{state ? `当前版本 ${state.currentVersion}` : ''}</span></div>
    {state?.status === 'downloading' && <div className="update-progress"><progress max="100" value={state.percent || 0} aria-label="安装包下载进度"/><span>{state.percent || 0}%</span></div>}
    <div className="update-actions"><span>{state?.status === 'available' ? '点击后下载并重启，会关闭本机访问、停止未完成任务。' : '每小时检查一次；未经点击，不下载、不安装。'}</span>{state?.status === 'available' ? <button className="primary" onClick={() => void act(true)}>更新并重启</button> : <button className="secondary" disabled={!!busy || state?.status === 'unsupported'} onClick={() => void act(false)}>{state?.status === 'checking' ? '检查中…' : state?.status === 'downloading' ? '正在下载…' : state?.status === 'installing' ? '正在安装…' : '检查更新'}</button>}</div>
  </section>
}
