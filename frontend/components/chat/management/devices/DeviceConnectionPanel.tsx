'use client'

import { useEffect, useState } from 'react'
import { getApiBaseUrl } from '../../utils'
import { DeviceCopyField } from './DeviceCopyField'
import styles from './DeviceConnectionPanel.module.css'

/** 集中展示本机助手需要的服务器地址与本次配对码。
 * Args:
 *   code: 本次生成的配对码。
 *   remaining: 配对码剩余有效秒数。
 *   onCollapse: 收起本次配对码。
 */
export function DeviceConnectionPanel({ code, remaining, onCollapse }: { code?: string; remaining: number; onCollapse: () => void }) {
  const [serverAddress, setServerAddress] = useState('')
  useEffect(() => { setServerAddress(getApiBaseUrl()) }, [])
  return <section className={styles.panel} aria-label="本机助手连接信息">
    <div className={styles.heading}><h2>连接本机助手</h2><p>把下面的服务器地址粘贴到本机助手的「服务器地址」中。</p></div>
    <DeviceCopyField label="服务器地址" value={serverAddress}/>
    {code ? <div className={styles.pairing}>
      <DeviceCopyField label="配对码" value={remaining ? code : '配对码已过期，请重新生成'} disabled={!remaining}/>
      <div className={styles.footer}><span>{remaining ? `${remaining} 秒后失效，只能使用一次。配对后访问默认关闭。` : '请点击「连接新设备」重新生成配对码。'}</span><button type="button" onClick={onCollapse}>收起配对码</button></div>
    </div> : <p className={styles.hint}>接下来，点击「连接新设备」生成配对码，在本机助手中完成配对。</p>}
  </section>
}
