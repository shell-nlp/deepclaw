import type { ReactNode } from 'react'

/** 显示设备与访问授权标志；Args: kind 图标类型。 */
export function DeviceIcon({ kind = 'device' }: { kind?: 'device' | 'shield' | 'folder' }) {
  return <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    {kind === 'device' ? <><rect x="4" y="5" width="24" height="17" rx="2"/><path d="M11 27h10M16 22v5M8 18h16"/></> : kind === 'shield' ? <><path d="m16 3 11 4v9c0 7-11 13-11 13S5 23 5 16V7z"/><path d="m10.5 15.5 4 4 7-8"/></> : <path d="M4 10V7h9l3 4h12v15H4V10z"/>}
  </svg>
}

/** 可访问的开关按钮；Args: checked 当前状态, disabled 禁用, label 可访问名称, onChange 切换回调。 */
export function Toggle({ checked, disabled, label, onChange }: { checked: boolean; disabled?: boolean; label: string; onChange: () => void }) {
  return <button type="button" className="switch" role="switch" aria-label={label} aria-checked={checked} disabled={disabled} onClick={onChange}><span/></button>
}

/** 具有一致间距的设置行；Args: title 标题, children 描述, control 操作控件。 */
export function SettingRow({ title, children, control }: { title: string; children: ReactNode; control: ReactNode }) {
  return <div className="setting-row"><div><strong>{title}</strong><p>{children}</p></div>{control}</div>
}
