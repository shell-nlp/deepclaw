'use client'

import { useId, useRef, useState } from 'react'
import styles from './DeviceConnectionPanel.module.css'

/** 展示可选中及复制的连接信息，并反馈复制结果。
 * Args:
 *   label: 字段名称。
 *   value: 完整字段值。
 *   disabled: 是否禁止复制。
 */
export function DeviceCopyField({ label, value, disabled = false }: { label: string; value: string; disabled?: boolean }) {
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const [copiedValue, setCopiedValue] = useState('')
  const [failedValue, setFailedValue] = useState('')
  const [copying, setCopying] = useState(false)
  const copied = !!value && copiedValue === value && !disabled
  const failed = !!value && failedValue === value && !disabled

  /** 复制完整文本，剪贴板不可用时从当前字段兼容复制。
   * Args:
   *   无。
   */
  async function copy() {
    if (!value || disabled || copying) return
    setCopying(true); setFailedValue(''); setCopiedValue('')
    try {
      try { await navigator.clipboard.writeText(value) }
      catch {
        input.current?.focus()
        input.current?.select()
        if (!document.execCommand('copy')) throw new Error('复制未成功')
      }
      setCopiedValue(value)
    } catch { setFailedValue(value) }
    finally { setCopying(false) }
  }

  return <div className={styles.field}>
    <label htmlFor={id}>{label}</label>
    <div className={styles.valueRow}>
      <input id={id} ref={input} readOnly value={value} placeholder="正在获取地址…" spellCheck={false} onFocus={event => event.currentTarget.select()}/>
      <button type="button" disabled={!value || disabled || copying} onClick={() => void copy()} aria-label={`复制${label}`} data-copied={copied}>
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">{copied ? <path d="m4 10 4 4 8-8"/> : <><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M12 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h2"/></>}</svg>
        {copying ? '复制中…' : copied ? '已复制' : '复制'}
      </button>
    </div>
    <span className={styles.feedback} role="status">{failed ? '自动复制失败，请选中文本后按 Ctrl+C，或使用系统复制菜单。' : copied ? `${label}已复制` : ''}</span>
  </div>
}
