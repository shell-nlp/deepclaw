'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ActorState } from '../utils/auth'

export interface ClientDevice {
  id: string; name: string; platform: string; online: boolean; enabled: boolean
  revision: number; capabilities: string[]; roots: string[]; last_seen: number
}
export interface ClientDeviceTask {
  id: string; device_id: string; operation: string; arguments: Record<string, unknown>
  status: string; output: string; result: Record<string, unknown> | null; cancel_requested: boolean; created_at: number
}
export type DeviceRequest = <T>(path: string, init?: RequestInit) => Promise<T>

/** 按当前账号查询设备并维护本轮选择，账号变更时立即清除旧结果；Args: requestJson 鉴权请求, actor 当前身份。 */
export function useDevices(requestJson: DeviceRequest, actor: ActorState) {
  const [devices, setDevices] = useState<ClientDevice[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [revision, setRevision] = useState(0)
  const owner = actor.isGuest ? '' : actor.userId || ''
  const previousOwner = useRef(owner)
  const sameOwner = previousOwner.current === owner
  const visibleDevices = sameOwner ? devices : []
  useEffect(() => {
    previousOwner.current = owner; setDevices([]); setSelectedId(''); setError('')
  }, [owner])
  useEffect(() => {
    if (!owner) return
    const controller = new AbortController()
    let pending = false
    /** 更新设备快照，取消过期请求并禁止轮询重叠；Args: 无。 */
    async function load() {
      if (pending) return
      pending = true; setLoading(true)
      try {
        const data = await requestJson<{ items: ClientDevice[] }>('/api/devices', { signal: controller.signal })
        if (!controller.signal.aborted) { setDevices(data.items); setSelectedId(id => data.items.some(device => device.id === id && device.online && device.enabled) ? id : ''); setError('') }
      } catch { if (!controller.signal.aborted) { setDevices([]); setSelectedId(''); setError('设备状态加载失败，请刷新重试。') } }
      finally { pending = false; if (!controller.signal.aborted) setLoading(false) }
    }
    void load()
    const timer = window.setInterval(() => void load(), 10000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [requestJson, owner, revision])
  const available = visibleDevices.filter(device => device.online && device.enabled)
  const selectedDeviceId = available.some(device => device.id === selectedId) ? selectedId : ''
  const refresh = useCallback(() => setRevision(value => value + 1), [])
  return { devices: visibleDevices, available, selectedDeviceId, setSelectedDeviceId: setSelectedId, error, loading, refresh }
}
