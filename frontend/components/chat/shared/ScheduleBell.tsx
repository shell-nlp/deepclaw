import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import styles from '../management/Schedules.module.css'
import { displayScheduleTime, SCHEDULES_PATH } from '../management/schedules'
import type { RequestJson, ScheduleNotification } from '../management/schedules'
import { getApiUrl } from '../utils'
import { SidebarIcon } from './BrandIcons'

type NotificationPage = { unread: number; items: ScheduleNotification[] }
const PATH = SCHEDULES_PATH + '/notifications'

/**
 * 展示铃铛未读数量、执行通知和文件下载。
 *
 * Args:
 *   requestJson: 已鉴权的 JSON 请求。
 *   withAuthHeaders: 附加当前账号认证头。
 *   canManage: 是否有删除通知的权限。
 */
export function ScheduleBell({ requestJson, withAuthHeaders, canManage }: {
  requestJson: RequestJson
  withAuthHeaders: (headers?: HeadersInit) => HeadersInit
  canManage: boolean
}) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState<NotificationPage>({ unread: 0, items: [] })
  const [older, setOlder] = useState<ScheduleNotification[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [position, setPosition] = useState({ top: 0, right: 0 })
  const panel = useRef<HTMLElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const revision = useRef(0)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const current = ++revision.current
    try {
      const result = await requestJson<NotificationPage>(PATH, { signal })
      if (!signal?.aborted && current === revision.current) {
        setPage(result)
        setLoaded(true)
        setError('')
      }
    } catch {
      if (!signal?.aborted && current === revision.current) setError('通知加载失败。')
    }
  }, [requestJson])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    const timer = window.setInterval(() => void refresh(controller.signal), 10_000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [refresh])

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node
      if (!panel.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', updatePosition)
    panel.current?.focus()
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', updatePosition)
    }
  }, [open])

  /**
   * 根据铃铛在视口中的位置对齐通知面板。
   *
   * Args:
   *   无。
   */
  function updatePosition() {
    const rect = trigger.current?.getBoundingClientRect()
    if (rect) setPosition({ top: rect.bottom + 8, right: Math.max(12, document.documentElement.clientWidth - rect.right) })
  }

  const currentIds = new Set(page.items.map((item) => item.id))
  const items = [...page.items, ...older.filter((item) => !currentIds.has(item.id))]

  /**
   * 标记当前展示的通知为已读。
   *
   * Args:
   *   无。
   */
  async function markRead() {
    if (busy) return
    setBusy(true)
    const ids = items.filter((item) => !item.read_at).map((item) => item.id)
    try {
      for (let index = 0; index < ids.length; index += 50) {
        await requestJson(PATH + '/read', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: ids.slice(index, index + 50) }),
        })
      }
      const readAt = new Date().toISOString()
      setOlder((existing) => existing.map((item) => ({ ...item, read_at: item.read_at || readAt })))
      await refresh()
    } catch {
      setError('标记已读失败。')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 加载更早的通知。
   *
   * Args:
   *   无。
   */
  async function loadOlder() {
    const last = items.at(-1)
    if (!last || busy) return
    setBusy(true)
    try {
      const result = await requestJson<NotificationPage>(PATH + '?before=' + encodeURIComponent(last.id))
      setOlder((existing) => [...existing, ...result.items])
      setHasMore(result.items.length === 50)
    } catch {
      setError('较早通知加载失败。')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 删除单条通知及其附件。
   *
   * Args:
   *   item: 待删除的通知。
   */
  async function removeNotification(item: ScheduleNotification) {
    if (busy || !window.confirm(item.filename ? '删除这条通知及其附件？' : '删除这条通知？')) return
    setBusy(true)
    try {
      await requestJson(PATH + '/' + item.id, { method: 'DELETE' })
      setExpandedId(null)
      setOlder((existing) => existing.filter((entry) => entry.id !== item.id))
      setPage((current) => ({
        unread: item.read_at ? current.unread : Math.max(0, current.unread - 1),
        items: current.items.filter((entry) => entry.id !== item.id),
      }))
      await refresh()
      panel.current?.focus()
    } catch {
      setError('删除通知失败。')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 请求并保存当前账号有权下载的文件。
   *
   * Args:
   *   item: 包含文件名的执行通知。
   */
  async function download(item: ScheduleNotification) {
    if (!item.filename) return
    try {
      const response = await fetch(getApiUrl(PATH + '/' + item.id + '/file'), { headers: withAuthHeaders() })
      if (!response.ok) throw new Error('下载失败')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = item.filename
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch {
      setError('文件下载失败。')
    }
  }

  return <div className={styles.bellWrapper}>
    <button type="button" ref={trigger} className={styles.bell}
      aria-expanded={open} aria-label={page.unread ? '任务通知，' + page.unread + ' 条未读' : '任务通知'}
      onClick={() => {
        if (!open) {
          updatePosition()
          void refresh()
        }
        setOpen(!open)
      }}>
      <SidebarIcon name="notifications" />
      {page.unread > 0 && <span className={styles.badge} aria-hidden>{page.unread > 99 ? '99+' : page.unread}</span>}
    </button>
    {open && createPortal(<section ref={panel} tabIndex={-1} style={position} className={styles.notifications} aria-label="任务通知">
      <header>
        <h2>任务通知</h2>
        <button type="button" disabled={busy || !items.some((item) => !item.read_at)} onClick={() => void markRead()}>标记已读</button>
      </header>
      {error && <p className={styles.notificationError} role="alert">{error}</p>}
      {items.length === 0 && !error && <p className={styles.empty}>{loaded ? '暂无通知' : '正在加载通知…'}</p>}
      <ol>
        {items.map((item) => <li key={item.id} className={item.read_at ? undefined : styles.unread}>
          <button type="button" className={styles.notificationRow} aria-expanded={expandedId === item.id}
            onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}>
            <strong title={item.name}>{item.name}</strong>
            {item.status === 'failed' && <span className={styles.error}>失败</span>}
            <time dateTime={item.finished_at}>{displayScheduleTime(item.finished_at)}</time>
          </button>
          {expandedId === item.id && <div className={styles.notificationDetail}>
            <small>计划时间 {displayScheduleTime(item.scheduled_at)}</small>
            <p>{item.message}</p>
            <div className={styles.actions}>
              {item.filename && <button type="button" className={styles.download} onClick={() => void download(item)}>下载 {item.filename}</button>}
              {canManage && <button type="button" className={styles.danger} disabled={busy} onClick={() => void removeNotification(item)}>删除通知</button>}
            </div>
          </div>}
        </li>)}
      </ol>
      {hasMore && page.items.length === 50 && <button className={styles.more} type="button" disabled={busy} onClick={() => void loadOlder()}>加载更早通知</button>}
    </section>, document.body)}
  </div>
}

