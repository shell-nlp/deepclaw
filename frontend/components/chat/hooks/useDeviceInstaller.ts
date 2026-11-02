'use client'

import { useCallback, useEffect, useState } from 'react'
import { getApiUrl } from '../utils'

export type DeviceInstallerState =
  | { status: 'loading' | 'error' | 'unavailable' }
  | { status: 'available'; sizeBytes: number }

/** 查询公开安装包发布状态，失败时支持重试；Args: 无。 */
export function useDeviceInstaller() {
  const [installer, setInstaller] = useState<DeviceInstallerState>({ status: 'loading' })
  const [revision, setRevision] = useState(0)
  const retry = useCallback(() => { setInstaller({ status: 'loading' }); setRevision(value => value + 1) }, [])
  useEffect(() => {
    const controller = new AbortController()
    /** 获取当前服务器的安装包状态；Args: 无。 */
    async function load() {
      try {
        const response = await fetch(getApiUrl('/api/devices/installer'), { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error('下载服务不可用')
        const data = await response.json()
        if (typeof data.available !== 'boolean' || (data.available && !(typeof data.size_bytes === 'number' && data.size_bytes > 0))) throw new Error('安装包状态无效')
        if (!controller.signal.aborted) setInstaller(data.available ? { status: 'available', sizeBytes: data.size_bytes } : { status: 'unavailable' })
      } catch {
        if (!controller.signal.aborted) setInstaller({ status: 'error' })
      }
    }
    void load()
    return () => controller.abort()
  }, [revision])
  return { installer, retry }
}
