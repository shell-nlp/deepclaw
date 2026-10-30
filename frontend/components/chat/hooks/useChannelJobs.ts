'use client'

import { useEffect, useState } from 'react'

export interface ChannelJob {
  id: string
  channel: string
  binding_id: number | null
  message_id: string
  execution_status: string
  delivery_status: string
  attempts: number
  error: string | null
}

type RequestJson = <T>(path: string, init?: RequestInit) => Promise<T>

/**
 * 轮询渠道任务并提交安全补发或人工结束操作。
 *
 * Args:
 *   requestJson: 已鉴权的请求方法。
 *   scope: 当前用户或管理员查看范围。
 */
export function useChannelJobs(requestJson: RequestJson, scope: 'my' | 'all') {
  const [jobs, setJobs] = useState<ChannelJob[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let loading = false
    /**
     * 更新当前范围任务，避免轮询重叠及过期响应覆盖。
     *
     * Args:
     *   无。
     */
    async function load() {
      if (loading) return
      loading = true
      try {
        const data = await requestJson<{ items: ChannelJob[] }>(`/api/channels/jobs?scope=${scope}`, { signal: controller.signal })
        if (!controller.signal.aborted) {
          setJobs(data.items)
          setError('')
        }
      } catch {
        if (!controller.signal.aborted) setError('消息任务加载失败，请刷新重试。')
      } finally {
        loading = false
      }
    }
    setJobs([])
    void load()
    const timer = window.setInterval(() => void load(), 10000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [requestJson, scope, revision])

  /**
   * 补发已有结果或结束经过人工核对的异常任务。
   *
   * Args:
   *   id: 任务主键。
   *   action: 操作类型。
   */
  async function act(id: string, action: 'retry_delivery' | 'close') {
    if (busy) return
    setBusy(id)
    try {
      await requestJson(`/api/channels/jobs/${encodeURIComponent(id)}/actions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
      })
      setRevision((current) => current + 1)
    } catch {
      setError('操作失败，任务可能正在处理。请刷新后重试。')
    } finally {
      setBusy(null)
    }
  }
  return { jobs, error, busy, act }
}
