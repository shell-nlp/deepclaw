'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import { MODEL_API_PATH, MODEL_CATALOG_API_PATH } from '../utils/constants'
import type { ActorState } from '../utils/auth'
import { CHAT_UPSTREAM_FORMAT_LABELS, ModelEditor, modelPayload, type ChatUpstreamFormat, type ModelDraft, type ModelTestResult } from './ModelEditor'

type ModelType = 'chat' | 'embedding'
interface ModelItem { id: string; type: ModelType; name: string; provider: string; upstream_format?: ChatUpstreamFormat | null; api_base: string; api_key_masked: string; has_api_key: boolean; request_headers: string[]; context_window: number | null; created_at: string; updated_at: string; active: boolean }
interface Catalog { chat_models: ModelItem[]; embedding_models: ModelItem[]; active_chat_model_id: string | null; active_embedding_model_id: string | null }
interface Props { actor: ActorState; requestJson: <T>(path: string, init?: RequestInit) => Promise<T>; canManage?: boolean }
const emptyDraft = (type: ModelType): ModelDraft => ({ type, name: '', provider: 'OpenAI Compatible', upstream_format: 'chat_completions', api_base: '', api_key: '', context_window: '128000', request_headers: [] })

/**
 * 以模型目录形式管理大模型与语义模型。
 * Args:
 *   actor: 当前登录主体。
 *   requestJson: 带鉴权的 JSON 请求函数。
 */
export function ModelManagementView({ actor, requestJson, canManage = actor.role === 'admin' }: Props) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [draft, setDraft] = useState<ModelDraft | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const load = useCallback(async () => { setLoading(true); setError(''); try { setCatalog(await requestJson<Catalog>(MODEL_CATALOG_API_PATH)) } catch (cause) { setError(cause instanceof Error ? cause.message : '无法读取模型目录。') } finally { setLoading(false) } }, [requestJson])
  useEffect(() => { if (canManage && !actor.isGuest) void load() }, [actor.isGuest, canManage, load])
  const startCreate = (type: ModelType) => { setEditingId(null); setDraft(emptyDraft(type)); setNotice(''); setError('') }
  const startEdit = (model: ModelItem) => {
    setEditingId(model.id)
    setDraft({
      ...emptyDraft(model.type),
      name: model.name,
      provider: model.provider,
      upstream_format: model.upstream_format ?? 'chat_completions',
      api_base: model.api_base,
      context_window: String(model.context_window || 128000),
      request_headers: (model.request_headers ?? []).map((name, id) => ({ id, name, value: '', savedName: name })),
    })
    setNotice('')
    setError('')
  }
  const closeEditor = () => { if (!busy) { setDraft(null); setEditingId(null); setError('') } }
  const submit = async () => {
    if (!draft) return
    setBusy(true); setNotice(''); setError('')
    try {
      const body = modelPayload(draft)
      const next = editingId ? await requestJson<Catalog>(MODEL_API_PATH + '/' + editingId, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) : await requestJson<Catalog>(MODEL_API_PATH, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, type: draft.type }) })
      setCatalog(next); setDraft(null); setEditingId(null); setNotice(editingId ? '模型信息已更新。' : '模型已加入目录。')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存模型失败。') } finally { setBusy(false) }
  }
  const activate = async (model: ModelItem) => {
    setBusy(true); setNotice(''); setError('')
    try { setCatalog(await requestJson<Catalog>(MODEL_API_PATH + '/' + model.id + '/activate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: model.type }) })); setNotice('已切换到“' + model.name + '”。新请求会使用它。') } catch (cause) { setError(cause instanceof Error ? cause.message : '切换模型失败。') } finally { setBusy(false) }
  }
  const test = async (model: ModelItem) => {
    setTestingId(model.id); setNotice(''); setError('')
    try {
      const result = await requestJson<ModelTestResult>(MODEL_API_PATH + '/' + model.id + '/test', { method: 'POST' })
      const detail = result.dimension ? result.message + '，维度 ' + result.dimension : result.message
      ;(result.ok ? setNotice : setError)(detail + ' · ' + result.latency_ms + ' ms')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '模型测试失败。') } finally { setTestingId(null) }
  }
  const remove = async (model: ModelItem) => {
    if (model.active || !window.confirm('确定删除“' + model.name + '”吗？')) return
    setBusy(true); setNotice(''); setError('')
    try { setCatalog(await requestJson<Catalog>(MODEL_API_PATH + '/' + model.id, { method: 'DELETE' })); setNotice('模型已从目录移除。') } catch (cause) { setError(cause instanceof Error ? cause.message : '删除模型失败。') } finally { setBusy(false) }
  }
  if (actor.isGuest || !canManage) return <div className={styles.managementPage}><div className={styles.managementTopbar}><div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 模型管理</span><h2>模型管理</h2><p>模型目录属于系统级配置，仅管理员可以查看和修改。</p></div></div><div className={styles.managementPageGrid}><section className={styles.managementCard}><div className={styles.managementHeader}><h3>需要管理员权限</h3><span className={styles.accountRoleBadge}>{actor.isGuest ? '游客' : '普通用户'}</span></div><p className={styles.managementDescription}>管理员可以维护大模型和语义模型目录，并为每一类模型选择当前使用的版本。</p></section></div></div>
  const chatCount = catalog?.chat_models.length || 0
  const embeddingCount = catalog?.embedding_models.length || 0
  const editingModel = [...(catalog?.chat_models ?? []), ...(catalog?.embedding_models ?? [])].find((model) => model.id === editingId)
  return <div className={styles.managementPage}><div className={styles.managementNoticeRow}>{notice ? <div className={styles.managementNotice} role="status">{notice}</div> : null}{error && !draft ? <div className={styles.managementError} role="alert">{error}</div> : null}</div><div className={styles.managementTopbar + ' ' + styles.modelRegistryTopbar}><div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 模型管理</span><h2>模型目录</h2><p>把不同能力的模型收进同一张目录，明确谁负责思考，谁负责理解语义。</p></div><div className={styles.modelRegistrySummary}><strong>{loading ? '—' : chatCount + embeddingCount}</strong><span>个已登记模型</span></div></div><div className={styles.modelRegistryGrid}><ModelShelf title="大模型" subtitle="负责对话、推理与工具调用" type="chat" models={catalog?.chat_models || []} busy={busy || loading} testingId={testingId} onCreate={startCreate} onEdit={startEdit} onActivate={activate} onTest={test} onDelete={remove} /><ModelShelf title="语义模型" subtitle="负责知识库向量化与语义检索" type="embedding" models={catalog?.embedding_models || []} busy={busy || loading} testingId={testingId} onCreate={startCreate} onEdit={startEdit} onActivate={activate} onTest={test} onDelete={remove} /></div>{draft ? <ModelEditor draft={draft} modelId={editingId} hasSavedKey={Boolean(editingModel?.has_api_key)} busy={busy} error={error} requestJson={requestJson} onChange={(next) => { setError(''); setDraft(next) }} onClose={closeEditor} onSubmit={() => void submit()} /> : null}</div>
}

function ModelShelf({ title, subtitle, type, models, busy, testingId, onCreate, onEdit, onActivate, onTest, onDelete }: { title: string; subtitle: string; type: ModelType; models: ModelItem[]; busy: boolean; testingId: string | null; onCreate: (type: ModelType) => void; onEdit: (model: ModelItem) => void; onActivate: (model: ModelItem) => void; onTest: (model: ModelItem) => void; onDelete: (model: ModelItem) => void }) {
  const active = useMemo(() => models.find((item) => item.active), [models])
  return <section className={styles.managementCard + ' ' + styles.modelShelf}><div className={styles.modelShelfHeader}><div><div className={styles.modelShelfKicker}>{type === 'chat' ? 'REASONING' : 'SEMANTIC'}</div><h3>{title}</h3><p>{subtitle}</p></div><button type="button" className={styles.managementButton} onClick={() => onCreate(type)}>新建</button></div><div className={styles.modelActiveStrip}><span className={styles.modelPulse} />当前使用 <strong>{active?.name || '尚未选择'}</strong></div><div className={styles.modelList}>{models.length === 0 ? <div className={styles.managementEmpty}>还没有{title}，先登记一个模型。</div> : models.map((model) => <article key={model.id} className={styles.modelRow + (model.active ? ' ' + styles.modelRowActive : '')}><div className={styles.modelRowMark}>{model.active ? '✓' : type === 'chat' ? '✦' : '∿'}</div><div className={styles.modelRowBody}><div className={styles.modelRowTitle}><strong>{model.name}</strong>{model.active ? <span className={styles.modelActiveBadge}>使用中</span> : null}</div><span className={styles.modelRowMeta}>{type === 'chat' ? CHAT_UPSTREAM_FORMAT_LABELS[model.upstream_format ?? 'chat_completions'] : model.provider} · {model.api_base}</span><span className={styles.modelRowMeta}>{model.has_api_key ? 'Key ' + model.api_key_masked : '未配置 API Key'}{model.context_window ? ' · ' + model.context_window.toLocaleString() + ' tokens' : ''}</span></div><div className={styles.modelRowActions}>{!model.active ? <button type="button" className={styles.managementMinorButton} disabled={busy} onClick={() => onActivate(model)}>切换</button> : null}<button type="button" className={styles.managementMinorButton} disabled={busy || testingId === model.id} onClick={() => onTest(model)}>{testingId === model.id ? '测试中…' : '测试'}</button><button type="button" className={styles.managementMinorButton} disabled={busy} onClick={() => onEdit(model)}>编辑</button><button type="button" className={styles.managementDangerMinorButton} disabled={busy || model.active} onClick={() => onDelete(model)}>删除</button></div></article>)}</div></section>
}
