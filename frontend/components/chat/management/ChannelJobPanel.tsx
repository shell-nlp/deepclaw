'use client'

import { useState } from 'react'
import { useChannelJobs, type ChannelJob } from '../hooks/useChannelJobs'
import styles from './ChannelJobPanel.module.css'

interface ChannelJobListProps {
  jobs: ChannelJob[]
  error: string
  busy: string | null
  act: (id: string, action: 'retry_delivery' | 'close') => Promise<void>
}

/**
 * 展示渠道待处理和异常消息，补发操作只发送已有结果。
 *
 * Args:
 *   jobs: 当前可见任务。
 *   error: 请求错误提示。
 *   busy: 当前提交中的任务标识。
 *   act: 任务操作提交方法。
 */
export function ChannelJobList({ jobs, error, busy, act }: ChannelJobListProps) {
  const [confirming, setConfirming] = useState<string | null>(null)
  if (!jobs.length && !error) return null
  return <section className={styles.panel} aria-label="消息处理状态">
    <div className={styles.heading}><strong>消息处理状态</strong><span>待处理 {jobs.length} 条 · 每 10 秒更新</span></div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {jobs.map((job) => {
      const canRetry = ['completed', 'interrupted'].includes(job.execution_status) && ['failed', 'pending'].includes(job.delivery_status)
      const uncertain = job.execution_status === 'uncertain' || job.delivery_status === 'uncertain'
      const label = uncertain ? '需要核对' : job.error ? '等待恢复' : canRetry ? '等待投递' : '处理中'
      return <article className={styles.row} key={job.id}>
        <div className={styles.details}><span className={styles.status}>{label}</span><span>{job.channel === 'feishu' ? '飞书' : job.channel === 'weixin_clawbot' ? '微信' : '钉钉'}{job.binding_id !== null ? ` · 绑定 ${job.binding_id}` : ''}</span><code title={job.message_id}>{job.message_id}</code>
          {job.error && <p>{job.error}</p>}
        </div>
        <div className={styles.actions}>
          {canRetry && <button disabled={busy !== null} onClick={() => void act(job.id, 'retry_delivery')}>重试投递</button>}
          {(uncertain || job.error) && <button disabled={busy !== null} onClick={() => setConfirming(job.id)}>结束异常任务</button>}
        </div>
        {confirming === job.id && <div className={styles.confirm}>
          <p>请先核对工具执行和消息投递结果。结束该任务后，会话将继续处理后续消息。</p>
          <button disabled={busy !== null} onClick={() => { setConfirming(null); void act(job.id, 'close') }}>已核对，确认结束</button>
          <button onClick={() => setConfirming(null)}>取消</button>
        </div>}
      </article>
    })}
  </section>
}

/**
 * 加载并展示当前渠道的持久化消息任务。
 *
 * Args:
 *   requestJson: 已鉴权的请求方法。
 *   scope: 当前用户或管理员范围。
 *   channel: 当前渠道。
 */
export function ChannelJobPanel({ requestJson, scope, channel }: {
  requestJson: Parameters<typeof useChannelJobs>[0]
  scope: 'my' | 'all'
  channel: string
}) {
  const state = useChannelJobs(requestJson, scope)
  return <ChannelJobList {...state} jobs={state.jobs.filter((job) => job.channel === channel)} />
}
