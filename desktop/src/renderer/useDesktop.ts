import { useCallback, useEffect, useState } from 'react'
import type { DesktopBridge, DesktopState } from '../shared/protocol'
declare global { interface Window { deepclaw?: DesktopBridge } }

/** 订阅本机状态并统一管理操作错误；Args: 无。 */
export function useDesktop() {
  const [state, setState] = useState<DesktopState | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const bridge = window.deepclaw
  useEffect(() => {
    if (!bridge) { setError('请在 DeepClaw 桌面客户端中打开此页面'); return }
    let active = true
    bridge.state().then(value => { if (active) setState(value) }).catch(() => { if (active) setError('本机状态读取失败，请重新打开助手') })
    const unsubscribe = bridge.subscribe(value => { if (active) setState(value) })
    return () => { active = false; unsubscribe() }
  }, [bridge])
  const act = useCallback(async (action: (bridge: DesktopBridge) => Promise<void>) => {
    if (!bridge || busy) return
    setBusy(true); setError('')
    try { await action(bridge) }
    catch (reason) { setError(String((reason as Error).message).replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '')) }
    finally { setBusy(false) }
  }, [bridge, busy])
  return { state, error, busy, act }
}
