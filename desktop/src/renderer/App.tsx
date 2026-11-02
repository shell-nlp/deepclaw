import { useState } from 'react'
import { useDesktop } from './useDesktop'
import { DeviceIcon } from './components/Controls'
import { AccessPanel, RootsPanel } from './components/AccessPanel'
import { PairingPanel } from './components/PairingPanel'
import { TaskList } from './components/TaskList'

/** 编排本机控制台，业务操作通过受限桥接执行；Args: 无。 */
export function App() {
  const { state, error, busy, act } = useDesktop()
  const [confirmUnpair, setConfirmUnpair] = useState(false)
  const approvals = state?.tasks.filter(task => task.status === 'awaiting_approval' && ['write_file', 'run_command'].includes(task.operation)).length || 0
  return <div className="desktop-shell"><aside className="rail"><div className="brand"><span className="brand-symbol">D</span><strong>DeepClaw</strong></div><span className="rail-caption">本机助手</span><div className="rail-active"><DeviceIcon/><span>设备与访问</span></div><div className="rail-bottom"><span className="privacy-dot"/><p>本机授权<br/><small>控制权始终在你手中</small></p></div></aside>
    <main><header className="page-header"><div><h1>设备与访问</h1><p>让智能体在你的允许下，为你处理本机工作。</p></div><span className="connection" data-online={state?.connected}><i/>{state?.connected ? '已连接工作台' : state?.paired ? '等待连接' : '尚未配对'}</span></header>
      {(error || state?.error) && <div className="error-banner" role="alert">{error || state?.error}</div>}
      {!state ? <p className="loading">{error ? '请使用桌面客户端连接本机能力。' : '正在读取本机状态…'}</p> : !state.paired ? <PairingPanel name={state.name} busy={busy} act={act}/> : <>
        <div className="device-identity"><DeviceIcon/><div><strong>{state.name}</strong><span>{state.server}</span></div><button className="text-button" onClick={() => setConfirmUnpair(!confirmUnpair)}>解绑设备</button></div>
        {!!approvals && <div className="approval-notice" role="status"><span><strong>{approvals} 项操作等待你确认</strong><small>核对完整参数后，决定是否允许此次操作。</small></span><button className="secondary" onClick={() => document.getElementById('execution-records')?.scrollIntoView({ block: 'start' })}>查看操作</button></div>}
        {confirmUnpair && <div className="unpair-confirm"><p>解绑会关闭本机访问并移除本机凭据。再次使用需要重新配对；也可在网页撤销服务端凭据。</p><button className="secondary" disabled={busy} onClick={() => { void act(bridge => bridge.unpair()); setConfirmUnpair(false) }}>确认解绑</button><button className="text-button" onClick={() => setConfirmUnpair(false)}>取消</button></div>}
        <AccessPanel state={state} busy={busy} act={act}/><RootsPanel state={state} busy={busy} act={act}/><TaskList tasks={state.tasks} busy={busy} act={act}/>
      </>}
      <footer>关闭窗口后助手保留在托盘。退出或连接断开后，本机访问自动关闭。</footer>
    </main>
  </div>
}
