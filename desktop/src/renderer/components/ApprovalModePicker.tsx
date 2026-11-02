import { useId } from 'react'
import { APPROVAL_MODES } from '../../shared/approval'
import type { ApprovalMode } from '../../shared/protocol'
import './ApprovalModePicker.css'

/** 选择本机审批力度，明确自动执行与目录边界。
 * Args:
 *   value: 当前本机审批模式。
 *   disabled: 正在保存时禁用。
 *   enabled: 本机总开关状态。
 *   onChange: 本机模式修改回调。
 */
export function ApprovalModePicker({ value, disabled, enabled, onChange }: { value: ApprovalMode; disabled: boolean; enabled: boolean; onChange: (mode: ApprovalMode) => void }) {
  const name = useId()
  return <fieldset className="approval-mode-picker" disabled={disabled}>
    <legend>操作审批</legend>
    <p className="approval-mode-intro">决定智能体何时需要询问你。仅在这台电脑上设置。</p>
    <div className="approval-mode-options">{APPROVAL_MODES.map(mode => <label key={mode.value} className="approval-mode-option" data-selected={value === mode.value} data-mode={mode.value}>
      <input type="radio" name={name} value={mode.value} checked={value === mode.value} onChange={() => onChange(mode.value)}/>
      <svg className="approval-mode-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{mode.value === 'confirm' ? <><path d="M8 11V5a2 2 0 0 1 4 0v5-2a2 2 0 0 1 4 0v3-1a2 2 0 0 1 4 0v4c0 5-3 8-7 8-3 0-5-2-7-5l-2-3a2 2 0 0 1 3-2l2 2"/></> : <><path d="m12 2 8 3v6c0 6-8 11-8 11S4 17 4 11V5z"/><path d="M12 7v6m0 3v1"/></>}</svg>
      <span className="approval-mode-copy"><strong>{mode.title}{mode.value === 'confirm' && <small>默认</small>}</strong><span>{mode.description}</span></span>
      <span className="approval-mode-check" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m4 10 4 4 8-8"/></svg></span>
    </label>)}</div>
    <p className="approval-mode-boundary" role="status">{value === 'auto' ? <><strong>{enabled ? '完全访问已生效。' : '开启总开关后生效。'}</strong>文件工具仍限授权目录，未开启的能力仍不可用。命令拥有当前账户权限，可能访问目录外的文件或网络。</> : '读取授权目录无需确认；每次修改文件或运行命令，都由你在本机批准。'}</p>
    <p className="approval-mode-footnote">切换模式会停止未完成任务。重启或断线后，总开关仍会自动关闭。</p>
  </fieldset>
}
