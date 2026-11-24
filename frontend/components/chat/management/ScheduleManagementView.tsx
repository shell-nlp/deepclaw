import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import styles from './Schedules.module.css'
import { displayScheduleTime, localDateTime, SCHEDULES_PATH } from './schedules'
import type { RequestJson, ScheduleSettings, ScheduledTask } from './schedules'

const OUTPUT_LABELS = { notification: '文字提醒', md: 'Markdown 文件', docx: 'Word 文件' }

/**
 * 创建新任务表单的默认值。
 *
 * Args:
 *   无。
 */
function newSettings(): ScheduleSettings {
  return {
    name: '', content: '', cron: null, run_at: '', interval_seconds: null,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
    mode: 'literal', output: 'notification', enabled: true,
  }
}

/**
 * 管理当前账号的定时任务。
 *
 * Args:
 *   requestJson: 已鉴权的 JSON 请求。
 *   isGuest: 是否为游客。
 *   canView: 是否可查看任务。
 *   canManage: 是否可管理任务。
 *   onLogin: 打开登录页。
 */
export function ScheduleManagementView({ requestJson, isGuest, canView, canManage, onLogin }: {
  requestJson: RequestJson
  isGuest: boolean
  canView: boolean
  canManage: boolean
  onLogin: () => void
}) {
  const [jobs, setJobs] = useState<ScheduledTask[]>([])
  const [loaded, setLoaded] = useState(false)
  const [draft, setDraft] = useState<ScheduleSettings | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<ScheduledTask | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!canView) return
    const controller = new AbortController()
    const load = () => requestJson<ScheduledTask[]>(SCHEDULES_PATH, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) {
          setJobs(result)
          setLoaded(true)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('定时任务加载失败。')
      })
    void load()
    const timer = window.setInterval(() => void load(), 15_000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [canView, requestJson])

  /**
   * 打开新建或编辑表单。
   *
   * Args:
   *   job: 已保存的任务，新建时省略。
   */
  function openEditor(job?: ScheduledTask) {
    setError('')
    setDeleting(null)
    setEditing(job?.id ?? null)
    setDraft(job?.settings ?? newSettings())
  }

  /**
   * 保存任务表单。
   *
   * Args:
   *   event: 表单提交事件。
   */
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!draft || busy) return
    setBusy(true)
    setError('')
    try {
      const saved = await requestJson<ScheduledTask>(editing ? SCHEDULES_PATH + '/' + editing : SCHEDULES_PATH, {
        method: editing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      })
      setJobs((items) => [saved, ...items.filter((item) => item.id !== saved.id)])
      setLoaded(true)
      setDraft(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存任务失败。')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 删除经过确认的任务。
   *
   * Args:
   *   无。
   */
  async function remove() {
    if (!deleting || busy) return
    setBusy(true)
    setError('')
    try {
      await requestJson(SCHEDULES_PATH + '/' + deleting.id, { method: 'DELETE' })
      setJobs((items) => items.filter((item) => item.id !== deleting.id))
      setDeleting(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '删除任务失败。')
    } finally {
      setBusy(false)
    }
  }

  /**
   * 从任务列表直接暂停或启动任务。
   *
   * Args:
   *   job: 要切换状态的任务。
   */
  async function toggleEnabled(job: ScheduledTask) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await requestJson<ScheduledTask>(SCHEDULES_PATH + '/' + job.id + '/enabled', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !job.settings.enabled }),
      })
      setJobs((items) => items.map((item) => item.id === updated.id ? updated : item))
      if (editing === updated.id) {
        setDraft((current) => current && { ...current, enabled: updated.settings.enabled })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '更新任务状态失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={styles.page} aria-labelledby="schedule-heading">
      <header className={styles.pageHeader}>
        <div>
          <h1 id="schedule-heading">定时任务</h1>
          <p>安排一次或周期执行，完成后在通知中查看结果。</p>
        </div>
        {canManage && <button type="button" className={styles.primary} disabled={busy} onClick={() => openEditor()}>新建任务</button>}
      </header>
      {isGuest ? <div className={styles.empty}>
        <p>登录后可管理定时任务并接收通知。</p>
        <button type="button" className={styles.primary} onClick={onLogin}>登录</button>
      </div> : <>
        {error && <p className={styles.error} role="alert">{error}</p>}
        {canManage && draft && <form className={styles.editor} onSubmit={save}>
          <h2>{editing ? '编辑任务' : '新建任务'}</h2>
          <fieldset disabled={busy}>
            <label className={styles.full}>任务名称<input required maxLength={120} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label>执行频率<select value={draft.interval_seconds !== null ? 'interval' : draft.cron !== null ? 'cron' : 'once'} onChange={(e) => setDraft({
              ...draft,
              cron: e.target.value === 'cron' ? '0 9 * * *' : null,
              run_at: e.target.value === 'once' ? '' : null,
              interval_seconds: e.target.value === 'interval' ? 10 : null,
            })}>
              <option value="once">仅执行一次</option>
              <option value="interval">按固定间隔执行</option>
              <option value="cron">按 Cron 周期执行</option>
            </select></label>
            {draft.interval_seconds !== null ?
              <label>间隔（秒）<input required type="number" min="1" step="1"
                value={draft.interval_seconds || ''}
                onChange={(e) => setDraft({ ...draft, interval_seconds: Number(e.target.value) })} /></label> :
              draft.cron === null ?
              <label>执行时间（本地时间）<input required type="datetime-local" step="1"
                value={draft.run_at ? localDateTime(draft.run_at) : ''}
                onChange={(e) => setDraft({ ...draft, run_at: e.target.value ? new Date(e.target.value).toISOString() : '' })} /></label> :
              <>
                <label>Cron 表达式
                  <input required maxLength={120} value={draft.cron} aria-describedby="schedule-cron-hint"
                    onChange={(e) => setDraft({ ...draft, cron: e.target.value })} />
                  <small id="schedule-cron-hint">五段为分、时、日、月、周。六段在最前面加秒。</small>
                </label>
                <label>时区<input required maxLength={80} placeholder="Asia/Shanghai" value={draft.timezone} onChange={(e) => setDraft({ ...draft, timezone: e.target.value })} /></label>
              </>
            }
            <label>输出格式<select value={draft.output} onChange={(e) => setDraft({ ...draft, output: e.target.value as ScheduleSettings['output'] })}>
              {Object.entries(OUTPUT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>内容来源<select value={draft.mode} onChange={(e) => setDraft({ ...draft, mode: e.target.value as ScheduleSettings['mode'] })}>
              <option value="literal">使用填写的内容</option><option value="generate">执行时由模型生成</option>
            </select></label>
            <label className={styles.full}>
              {draft.mode === 'generate' ? '生成要求' : '内容正文'}
              <textarea required rows={4} maxLength={16000} value={draft.content} onChange={(e) => setDraft({ ...draft, content: e.target.value })} />
            </label>
            <label className={styles.checkbox}><input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />启用任务</label>
            <div className={styles.actions}>
              <button type="button" onClick={() => setDraft(null)}>取消</button>
              <button type="submit" className={styles.primary}>{busy ? '保存中…' : '保存任务'}</button>
            </div>
          </fieldset>
        </form>}
        {deleting && <div className={styles.confirm}>
          <p>删除「{deleting.settings.name}」？已生成的结果仍可在通知中查看。</p>
          <div className={styles.actions}>
            <button type="button" disabled={busy} onClick={() => setDeleting(null)}>取消</button>
            <button type="button" className={styles.danger} disabled={busy} onClick={() => void remove()}>删除任务</button>
          </div>
        </div>}
        {!canView && <p className={styles.empty}>当前账号没有查看定时任务的权限。</p>}
        {canView && !loaded && !error && <p className={styles.empty}>正在加载任务…</p>}
        {canView && loaded && jobs.length === 0 && !draft && <p className={styles.empty}>暂无任务。</p>}
        <ul className={styles.taskList}>
          {canView && jobs.map((job) => <li key={job.id} className={styles.task}>
            <div>
              <h2>{job.settings.name}</h2>
              <p>{job.settings.interval_seconds !== null ? `每 ${job.settings.interval_seconds} 秒`
                : job.settings.cron ? job.settings.cron + ' · ' + job.settings.timezone : displayScheduleTime(job.settings.run_at!)}
                {' · '}{OUTPUT_LABELS[job.settings.output]}</p>
            </div>
            <span className={styles.next}>
              {job.next_at ? <><small>下次执行</small><time dateTime={job.next_at}>{displayScheduleTime(job.next_at)}</time></>
                : job.settings.enabled ? '已触发' : '已暂停'}
            </span>
            {canManage && <div className={styles.actions}>
              {(!job.settings.enabled || job.next_at) && <button type="button" disabled={busy}
                onClick={() => void toggleEnabled(job)}>{job.settings.enabled ? '暂停' : '启动'}</button>}
              <button type="button" disabled={busy} onClick={() => openEditor(job)}>编辑</button>
              <button type="button" disabled={busy} onClick={() => { setDraft(null); setDeleting(job); setError('') }}>删除</button>
            </div>}
          </li>)}
        </ul>
      </>}
    </section>
  )
}

