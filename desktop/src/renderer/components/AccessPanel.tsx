import type { DesktopState, DesktopBridge } from '../../shared/protocol'
import { DeviceIcon, SettingRow, Toggle } from './Controls'
import { ApprovalModePicker } from './ApprovalModePicker'
type Act = (action: (bridge: DesktopBridge) => Promise<void>) => Promise<void>

/** 编排本机总开关和分项权限；Args: state 本机快照, busy 提交状态, act 本机操作入口。 */
export function AccessPanel({ state, busy, act }: { state: DesktopState; busy: boolean; act: Act }) {
  const { policy } = state
  return <section className="access-panel" data-enabled={policy.enabled}>
    <div className="access-head"><div className="shield"><DeviceIcon kind="shield"/></div><span className="access-badge">{policy.enabled ? '允许访问' : '访问已关闭'}</span></div>
    <div className="access-main"><div><h2>{policy.enabled ? '本机已向智能体开放' : '你的电脑，由你掌控'}</h2><p>{policy.enabled ? '智能体可以在下方授权范围内操作。随时关闭，即刻停止接收新任务。' : '打开后，智能体才能看到这台设备并使用已授权的能力。'}</p></div><Toggle label="允许智能体访问本机" checked={policy.enabled} disabled={busy || !state.connected || !policy.roots.length} onChange={() => void act(bridge => bridge.policy({ enabled: !policy.enabled }))}/></div>
    {!policy.roots.length && <p className="access-help">先在下方添加一个授权目录，再开启本机访问。</p>}
    <ApprovalModePicker value={policy.approvalMode} disabled={busy} enabled={policy.enabled} onChange={approvalMode => void act(bridge => bridge.policy({ approvalMode }))}/>
    <div className="permissions">
      <SettingRow title="读取文件" control={<span className="permission-note">授权目录内</span>}>允许浏览目录和读取文本文件。</SettingRow>
      <SettingRow title="修改文件" control={<Toggle label="允许修改文件" checked={policy.capabilities.includes('files.write')} disabled={busy} onChange={() => void act(bridge => bridge.policy({ allowWrite: !policy.capabilities.includes('files.write') }))}/>}>{policy.approvalMode === 'auto' ? '开启后，在授权目录内自动写入，无需逐次确认。' : '每次写入前，都需要你在本机确认。'}</SettingRow>
      <SettingRow title="运行命令" control={<Toggle label="允许运行命令" checked={policy.capabilities.includes('command.run')} disabled={busy} onChange={() => void act(bridge => bridge.policy({ allowCommand: !policy.capabilities.includes('command.run') }))}/>}>{policy.approvalMode === 'auto' ? '开启后自动执行，不再逐次询问。命令拥有当前账户权限。' : '执行前展示完整程序、参数和工作目录，由你确认。'}</SettingRow>
    </div>
  </section>
}

/** 管理通过原生对话框选择的目录；Args: state 本机快照, busy 提交状态, act 本机操作入口。 */
export function RootsPanel({ state, busy, act }: { state: DesktopState; busy: boolean; act: Act }) {
  return <section className="roots-panel"><div className="section-heading"><div><h3>授权目录</h3><p>文件工具只能访问这里的内容。变更授权会停止旧任务。</p></div><button className="secondary" disabled={busy} onClick={() => void act(bridge => bridge.addRoot())}>添加目录</button></div>
    {state.policy.roots.length ? <ul className="roots">{state.policy.roots.map(root => <li key={root}><DeviceIcon kind="folder"/><span title={root}>{root}</span><button className="text-button" disabled={busy} onClick={() => void act(bridge => bridge.removeRoot(root))} aria-label={`移除目录 ${root}`}>移除</button></li>)}</ul> : <div className="empty-roots"><DeviceIcon kind="folder"/><span>选择一个工作目录，开始授权</span></div>}
  </section>
}
