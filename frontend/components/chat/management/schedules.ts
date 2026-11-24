export const SCHEDULES_PATH = '/api/schedules'

export type RequestJson = <T>(path: string, init?: RequestInit) => Promise<T>

export type ScheduleSettings = {
  name: string
  content: string
  timezone: string
  cron: string | null
  interval_seconds: number | null
  run_at: string | null
  mode: 'literal' | 'generate'
  output: 'notification' | 'md' | 'docx'
  enabled: boolean
}

export type ScheduledTask = { id: string; settings: ScheduleSettings; next_at: string | null }

export type ScheduleNotification = {
  id: string
  name: string
  status: 'succeeded' | 'failed'
  scheduled_at: string
  finished_at: string
  read_at: string | null
  message: string
  filename: string | null
}

/**
 * 按浏览器时区展示日期和时间。
 *
 * Args:
 *   value: 后端返回的 UTC 时间。
 */
export function displayScheduleTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/**
 * 将 UTC 时间转换为 datetime-local 控件所需的本地时间。
 *
 * Args:
 *   value: 后端返回的 UTC 时间。
 */
export function localDateTime(value: string) {
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19)
}

