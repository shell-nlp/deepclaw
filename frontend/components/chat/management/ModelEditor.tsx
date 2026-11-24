'use client'

import { useEffect, useRef, useState, type FormEvent } from 'react'
import styles from '../../ChatInterface.module.css'
import editor from './ModelEditor.module.css'
import { MODEL_API_PATH } from '../utils/constants'

interface HeaderRow { id: number; name: string; value: string; savedName?: string }
export const CHAT_UPSTREAM_FORMAT_LABELS = {
  chat_completions: 'Chat Completions',
  responses: 'Responses（原生）',
}
export type ChatUpstreamFormat = keyof typeof CHAT_UPSTREAM_FORMAT_LABELS

export interface ModelDraft {
  type: 'chat' | 'embedding'
  name: string
  provider: string
  upstream_format: ChatUpstreamFormat
  api_base: string
  api_key: string
  context_window: string
  request_headers: HeaderRow[]
}
export interface ModelTestResult { ok: boolean; message: string; latency_ms: number; dimension: number | null }
interface Props {
  draft: ModelDraft
  modelId: string | null
  hasSavedKey: boolean
  busy: boolean
  error: string
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  onChange: (draft: ModelDraft) => void
  onClose: () => void
  onSubmit: () => void
}

/** 生成保存与试连共用的表单数据。Args: draft 为当前表单。 */
export function modelPayload(draft: ModelDraft) {
  return {
    name: draft.name.trim(),
    provider: draft.provider.trim(),
    upstream_format: draft.type === 'chat' ? draft.upstream_format : null,
    api_base: draft.api_base.trim(),
    api_key: draft.api_key.trim() || null,
    context_window: draft.type === 'chat' ? Number(draft.context_window) : null,
    request_headers: draft.request_headers.map(({ name, value }) => ({ name: name.trim(), value: value || null })),
  }
}

/** 渲染模型设置、凭据显隐与试连结果。Args: props 为当前配置和操作回调。 */
export function ModelEditor({ draft, modelId, hasSavedKey, busy, error, requestJson, onChange, onClose, onSubmit }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const form = useRef<HTMLFormElement>(null)
  const nextRow = useRef(draft.request_headers.length)
  const [visible, setVisible] = useState(false)
  const [revealing, setRevealing] = useState(false)
  const [savedKey, setSavedKey] = useState('')
  const [keyError, setKeyError] = useState('')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<ModelTestResult | null>(null)
  const [testError, setTestError] = useState('')

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  /** 更新表单并清除旧配置的试连结果。Args: patch 为需要修改的字段。 */
  const change = (patch: Partial<ModelDraft>) => {
    setResult(null)
    setTestError('')
    setKeyError('')
    onChange({ ...draft, ...patch })
  }

  /** 显示或隐藏当前密钥。 */
  const toggleKey = async () => {
    setKeyError('')
    if (visible) {
      setVisible(false)
      setSavedKey('')
      return
    }
    if (draft.api_key || !hasSavedKey || !modelId) {
      setVisible(true)
      return
    }
    setRevealing(true)
    try {
      const secret = await requestJson<{ api_key: string }>(MODEL_API_PATH + '/' + modelId + '/reveal-key', { method: 'POST' })
      setSavedKey(secret.api_key)
      setVisible(true)
    } catch {
      setKeyError('无法查看密钥，请重试。')
    } finally {
      setRevealing(false)
    }
  }

  /** 使用当前未保存表单发起试连。 */
  const testConnection = async () => {
    if (!form.current?.reportValidity()) return
    setTesting(true)
    setResult(null)
    setTestError('')
    try {
      setResult(await requestJson<ModelTestResult>(MODEL_API_PATH + '/test-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...modelPayload(draft), type: draft.type, model_id: modelId }),
      }))
    } catch (cause) {
      setTestError(cause instanceof Error ? cause.message : '无法完成模型测试。')
    } finally {
      setTesting(false)
    }
  }

  /** 保存通过浏览器校验的表单。Args: event 为表单提交事件。 */
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!busy && !testing && !revealing) onSubmit()
  }

  const keyLabel = visible ? '隐藏 API Key' : '显示 API Key'
  const locked = busy || testing || revealing
  const valid = Boolean(draft.name.trim() && draft.api_base.trim())
  return (
    <dialog ref={dialog} className={editor.dialog} aria-labelledby="model-editor-title" onCancel={(event) => { event.preventDefault(); onClose() }}>
      <form ref={form} className={editor.form} onSubmit={submit}>
        <header className={editor.heading}>
          <div>
            <h3 id="model-editor-title">{modelId ? '编辑模型' : '登记模型'}</h3>
            <p>{draft.type === 'chat' ? '大模型 · 对话与推理' : '语义模型 · 向量化与检索'}</p>
          </div>
          <button type="button" className={editor.icon} aria-label="关闭" disabled={busy} onClick={onClose}>×</button>
        </header>

        <fieldset className={editor.content} disabled={locked}>
          <h4>连接设置</h4>
          <div className={editor.fields}>
            <label className={styles.managementField}>
              <span>模型名称</span>
              <input className={styles.managementInput} value={draft.name} onChange={(event) => change({ name: event.target.value })} placeholder={draft.type === 'chat' ? 'deepseek-chat' : 'bge-m3'} maxLength={200} required autoFocus />
            </label>
            <label className={styles.managementField}>
              {draft.type === 'chat' ? <>
                <span>上游格式</span>
                <select className={styles.managementInput} value={draft.upstream_format}
                  onChange={(event) => change({ upstream_format: event.target.value as ChatUpstreamFormat })}>
                  <option value="chat_completions">{CHAT_UPSTREAM_FORMAT_LABELS.chat_completions}</option>
                  <option value="responses">{CHAT_UPSTREAM_FORMAT_LABELS.responses}</option>
                </select>
              </> : <>
                <span>服务提供方</span>
                <input className={styles.managementInput} value={draft.provider} onChange={(event) => change({ provider: event.target.value })} placeholder="OpenAI Compatible" maxLength={100} />
              </>}
            </label>
            <label className={styles.managementField + ' ' + editor.full}>
              <span>API Base URL</span>
              <input className={styles.managementInput + ' ' + editor.technical} type="url" value={draft.api_base} onChange={(event) => change({ api_base: event.target.value })} placeholder="https://api.example.com/v1" maxLength={500} required />
            </label>
            <div className={styles.managementField + (draft.type === 'embedding' ? ' ' + editor.full : '')}>
              <label htmlFor="model-api-key">API Key {hasSavedKey && <small className={editor.saved}>已配置</small>}</label>
              <div className={editor.key}>
                <input id="model-api-key" className={styles.managementInput + ' ' + editor.technical} type={visible ? 'text' : 'password'} value={draft.api_key || savedKey} onChange={(event) => { setSavedKey(''); change({ api_key: event.target.value }) }} placeholder={hasSavedKey ? '••••••••••••' : '输入 API Key'} autoComplete="new-password" spellCheck={false} maxLength={2000} />
                <button className={editor.icon} type="button" title={keyLabel} aria-label={keyLabel} aria-pressed={visible} onClick={() => void toggleKey()}>
                  <span className={editor.eye} data-hidden={!visible} aria-hidden="true" />
                </button>
              </div>
              {keyError && <small role="alert" className={editor.failed}>{keyError}</small>}
            </div>
            {draft.type === 'chat' && <label className={styles.managementField}>
              <span>上下文窗口</span>
              <input className={styles.managementInput + ' ' + editor.technical} type="number" min="1" max="10000000" value={draft.context_window} onChange={(event) => change({ context_window: event.target.value })} required />
            </label>}
          </div>

          <section className={editor.headers} aria-labelledby="model-headers-title">
            <div className={editor.headersHeading}>
              <h4 id="model-headers-title">请求头 <span>{draft.request_headers.length}</span></h4>
              <button type="button" className={styles.managementMinorButton} disabled={draft.request_headers.length >= 32} onClick={() => change({ request_headers: [...draft.request_headers, { id: nextRow.current++, name: '', value: '' }] })}>＋ 添加请求头</button>
            </div>
            {draft.request_headers.length === 0 && <p className={editor.empty}>可为模型网关添加自定义请求头，例如 Host。</p>}
            {draft.request_headers.map((row, index) => {
              const keep = row.savedName?.toLowerCase() === row.name.trim().toLowerCase()
              return (
                <div className={editor.headerRow} key={row.id}>
                  <input aria-label={'请求头名称 ' + (index + 1)} className={styles.managementInput + ' ' + editor.technical} placeholder="X-API-Version" value={row.name} maxLength={128} required onChange={(event) => change({ request_headers: draft.request_headers.map((item) => item.id === row.id ? { ...item, name: event.target.value } : item) })} />
                  <input aria-label={'请求头值 ' + (index + 1)} className={styles.managementInput + ' ' + editor.technical} type="password" autoComplete="new-password" placeholder={keep ? '已保存 · 留空保留' : row.name.trim().toLowerCase() === 'host' ? '域名或 IP，可带端口' : '请求头值'} required={!keep} maxLength={8192} value={row.value} onChange={(event) => change({ request_headers: draft.request_headers.map((item) => item.id === row.id ? { ...item, value: event.target.value } : item) })} />
                  <button type="button" className={editor.icon} aria-label={'删除请求头 ' + (index + 1)} title="删除请求头" onClick={() => change({ request_headers: draft.request_headers.filter((item) => item.id !== row.id) })}>×</button>
                </div>
              )
            })}
          </section>
        </fieldset>

        <footer className={editor.footer}>
          <div className={editor.status} role="status">
            {error || testError ? <strong className={editor.failed}>{error || testError}</strong> :
              result ? <><strong className={result.ok ? editor.passed : editor.failed}>{result.message}</strong><small>{result.latency_ms} ms{result.dimension ? ' · ' + result.dimension + ' 维' : ''}</small></> :
                <small>{testing ? '正在连接模型服务…' : '可在保存前测试当前配置。'}</small>}
          </div>
          <div className={editor.actions}>
            <button type="button" className={styles.managementMinorButton} disabled={locked || !valid} onClick={() => void testConnection()}>{testing ? '测试中…' : '测试连接'}</button>
            <button type="submit" className={styles.managementButton} disabled={locked || !valid}>{busy ? '保存中…' : modelId ? '保存修改' : '登记模型'}</button>
          </div>
        </footer>
      </form>
    </dialog>
  )
}
