import { useState } from 'react'
import type { DesktopBridge } from '../../shared/protocol'
import { DeviceIcon } from './Controls'

/** 展示设备配对表单；Args: name 默认设备名称, busy 提交状态, act 本机操作入口。 */
export function PairingPanel({ name, busy, act }: { name: string; busy: boolean; act: (action: (bridge: DesktopBridge) => Promise<void>) => Promise<void> }) {
  const [server, setServer] = useState('')
  const [code, setCode] = useState('')
  const [deviceName, setDeviceName] = useState(name || '我的电脑')
  return <section className="pairing-panel"><div className="pairing-mark"><DeviceIcon/></div><h2>连接你的工作台</h2><p>在网页「我的设备」中生成配对码，将这台电脑绑定到你的账户。</p>
    <form onSubmit={event => { event.preventDefault(); void act(bridge => bridge.pair(server, code, deviceName)) }}>
      <label>服务器地址<input type="url" required placeholder="https://deepclaw.example.com" value={server} onChange={event => setServer(event.target.value)}/></label>
      <label>设备名称<input required maxLength={80} value={deviceName} onChange={event => setDeviceName(event.target.value)}/></label>
      <label>配对码<input required autoComplete="off" spellCheck={false} placeholder="粘贴网页生成的配对码" value={code} onChange={event => setCode(event.target.value)}/></label>
      <button className="primary" disabled={busy}>{busy ? '正在配对…' : '配对这台电脑'}</button>
    </form><p className="fine-print">配对不会开启本机访问。首次连接后，请选择目录并手动打开开关。</p>
  </section>
}
