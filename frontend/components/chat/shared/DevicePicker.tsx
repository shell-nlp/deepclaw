import type { ClientDevice } from '../hooks/useDevices'
import styles from './DevicePicker.module.css'

/** 仅允许选择在线且已开启的设备，本轮不选择时不提供本机工具；Args: devices 可用设备, value 设备标识, disabled 禁用, onChange 选择回调。 */
export function DevicePicker({ devices, value, disabled, onChange }: { devices: ClientDevice[]; value: string; disabled?: boolean; onChange: (id: string) => void }) {
  if (!devices.length) return null
  return <label className={styles.picker}><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/></svg><select aria-label="本轮使用的客户端设备" value={value} disabled={disabled} onChange={event => onChange(event.target.value)}><option value="">不使用本机设备</option>{devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>
}
