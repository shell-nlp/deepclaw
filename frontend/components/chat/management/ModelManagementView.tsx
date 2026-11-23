'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import { MODEL_API_PATH, MODEL_CATALOG_API_PATH } from '../utils/constants'
import type { ActorState } from '../utils/auth'

type ModelType = 'chat' | 'embedding'
interface ModelItem { id: string; type: ModelType; name: string; provider: string; api_base: string; api_key_masked: string; has_api_key: boolean; context_window: number | null; created_at: string; updated_at: string; active: boolean }
interface Catalog { chat_models: ModelItem[]; embedding_models: ModelItem[]; active_chat_model_id: string | null; active_embedding_model_id: string | null }
interface Draft { type: ModelType; name: string; provider: string; api_base: string; api_key: string; context_window: string }
interface Props { actor: ActorState; requestJson: <T>(path: string, init?: RequestInit) => Promise<T> }
const emptyDraft = (type: ModelType): Draft => ({ type, name: '', provider: 'OpenAI Compatible', api_base: '', api_key: '', context_window: '128000' })

/**
 * 以模型目录形式管理大模型与语义模型。
 * Args:
 *   actor: 当前登录主体。
 *   requestJson: 带鉴权的 JSON 请求函数。
 */
export function ModelManagementView({ actor, requestJson }: Props) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const load = useCallback(async () => { setLoading(true); setError(''); try { setCatalog(await requestJson<Catalog>(MODEL_CATALOG_API_PATH)) } catch (cause) { setError(cause instanceof Error ? cause.message : '无法读取模型目录。') } finally { setLoading(false) } }, [requestJson])
  const canManage = actor.role === 'admin' || Boolean(actor.permissions?.some((item) => item.action === 'write' && item.path === '/api/models'))
  useEffect(() => { if (canManage && !actor.isGuest) void load() }, [actor.isGuest, canManage, load])
  const startCreate = (type: ModelType) => { setEditingId(null); setDraft(emptyDraft(type)); setNotice(''); setError('') }
  const startEdit = (model: ModelItem) => { setEditingId(model.id); setDraft({ type: model.type, name: model.name, provider: model.provider, api_base: model.api_base, api_key: '', context_window: String(model.context_window || 128000) }); setNotice(''); setError('') }
  const closeEditor = () => { if (!busy) { setDraft(null); setEditingId(null) } }
  const submit = async () => {
    if (!draft) return
    setBusy(true); setNotice(''); setError('')
    try {
      const body = { name: draft.name.trim(), provider: draft.provider.trim(), api_base: draft.api_base.trim(), api_key: draft.api_key.trim() || null, context_window: Number(draft.context_window) }
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
      const result = await requestJson<{ ok: boolean; message: string; latency_ms: number; dimension: number | null }>(MODEL_API_PATH + '/' + model.id + '/test', { method: 'POST' })
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
  return <div className={styles.managementPage}><div className={styles.managementNoticeRow}>{notice ? <div className={styles.managementNotice} role="status">{notice}</div> : null}{error ? <div className={styles.managementError} role="alert">{error}</div> : null}</div><div className={styles.managementTopbar + ' ' + styles.modelRegistryTopbar}><div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 模型管理</span><h2>模型目录</h2><p>把不同能力的模型收进同一张目录，明确谁负责思考，谁负责理解语义。</p></div><div className={styles.modelRegistrySummary}><strong>{loading ? '—' : chatCount + embeddingCount}</strong><span>个已登记模型</span></div></div><div className={styles.modelRegistryGrid}><ModelShelf title="大模型" subtitle="负责对话、推理与工具调用" type="chat" models={catalog?.chat_models || []} busy={busy || loading} testingId={testingId} onCreate={startCreate} onEdit={startEdit} onActivate={activate} onTest={test} onDelete={remove} /><ModelShelf title="语义模型" subtitle="负责知识库向量化与语义检索" type="embedding" models={catalog?.embedding_models || []} busy={busy || loading} testingId={testingId} onCreate={startCreate} onEdit={startEdit} onActivate={activate} onTest={test} onDelete={remove} /></div>{draft ? <ModelEditor draft={draft} editing={Boolean(editingId)} busy={busy} onChange={setDraft} onClose={closeEditor} onSubmit={() => void submit()} /> : null}</div>
}

function ModelShelf({ title, subtitle, type, models, busy, testingId, onCreate, onEdit, onActivate, onTest, onDelete }: { title: string; subtitle: string; type: ModelType; models: ModelItem[]; busy: boolean; testingId: string | null; onCreate: (type: ModelType) => void; onEdit: (model: ModelItem) => void; onActivate: (model: ModelItem) => void; onTest: (model: ModelItem) => void; onDelete: (model: ModelItem) => void }) {
  const active = useMemo(() => models.find((item) => item.active), [models])
  return <section className={styles.managementCard + ' ' + styles.modelShelf}><div className={styles.modelShelfHeader}><div><div className={styles.modelShelfKicker}>{type === 'chat' ? 'REASONING' : 'SEMANTIC'}</div><h3>{title}</h3><p>{subtitle}</p></div><button type="button" className={styles.managementButton} onClick={() => onCreate(type)}>新建</button></div><div className={styles.modelActiveStrip}><span className={styles.modelPulse} />当前使用 <strong>{active?.name || '尚未选择'}</strong></div><div className={styles.modelList}>{models.length === 0 ? <div className={styles.managementEmpty}>还没有{title}，先登记一个模型。</div> : models.map((model) => <article key={model.id} className={styles.modelRow + (model.active ? ' ' + styles.modelRowActive : '')}><div className={styles.modelRowMark}>{model.active ? '✓' : type === 'chat' ? '✦' : '∿'}</div><div className={styles.modelRowBody}><div className={styles.modelRowTitle}><strong>{model.name}</strong>{model.active ? <span className={styles.modelActiveBadge}>使用中</span> : null}</div><span className={styles.modelRowMeta}>{model.provider} · {model.api_base}</span><span className={styles.modelRowMeta}>{model.has_api_key ? 'Key ' + model.api_key_masked : '未配置 API Key'}{model.context_window ? ' · ' + model.context_window.toLocaleString() + ' tokens' : ''}</span></div><div className={styles.modelRowActions}>{!model.active ? <button type="button" className={styles.managementMinorButton} disabled={busy} onClick={() => onActivate(model)}>切换</button> : null}<button type="button" className={styles.managementMinorButton} disabled={busy || testingId === model.id} onClick={() => onTest(model)}>{testingId === model.id ? '测试中…' : '测试'}</button><button type="button" className={styles.managementMinorButton} disabled={busy} onClick={() => onEdit(model)}>编辑</button><button type="button" className={styles.managementDangerMinorButton} disabled={busy || model.active} onClick={() => onDelete(model)}>删除</button></div></article>)}</div></section>
}

function ModelEditor({ draft, editing, busy, onChange, onClose, onSubmit }: { draft: Draft; editing: boolean; busy: boolean; onChange: (draft: Draft) => void; onClose: () => void; onSubmit: () => void }) {
  return <div className={styles.modelEditorBackdrop} role="presentation"><section className={styles.modelEditor} role="dialog" aria-modal="true" aria-labelledby="model-editor-title"><div className={styles.modelEditorHeader}><div><span className={styles.modelShelfKicker}>{draft.type === 'chat' ? 'REASONING MODEL' : 'SEMANTIC MODEL'}</span><h3 id="model-editor-title">{editing ? '编辑模型' : '登记新模型'}</h3></div><button type="button" className={styles.managementMinorButton} onClick={onClose}>关闭</button></div><div className={styles.modelEditorForm}><label className={styles.managementField}><span>模型名称</span><input className={styles.managementInput} value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} placeholder={draft.type === 'chat' ? 'deepseek-chat' : 'bge-m3'} autoFocus /></label><label className={styles.managementField}><span>服务提供方</span><input className={styles.managementInput} value={draft.provider} onChange={(event) => onChange({ ...draft, provider: event.target.value })} placeholder="OpenAI Compatible" /></label><label className={styles.managementField}><span>API Base URL</span><input className={styles.managementInput} value={draft.api_base} onChange={(event) => onChange({ ...draft, api_base: event.target.value })} placeholder="https://api.example.com/v1" /></label><label className={styles.managementField}><span>API Key <small>留空则保持原值</small></span><input className={styles.managementInput} type="password" value={draft.api_key} onChange={(event) => onChange({ ...draft, api_key: event.target.value })} autoComplete="new-password" /></label>{draft.type === 'chat' ? <label className={styles.managementField}><span>上下文窗口</span><input className={styles.managementInput} type="number" min="1" value={draft.context_window} onChange={(event) => onChange({ ...draft, context_window: event.target.value })} /></label> : null}</div><div className={styles.modelEditorFooter}><span className={styles.managementMeta}>密钥只保存在服务端，并以脱敏形式展示。</span><button type="button" className={styles.managementButton} disabled={busy || !draft.name.trim() || !draft.api_base.trim()} onClick={onSubmit}>{busy ? '保存中…' : editing ? '保存修改' : '登记模型'}</button></div></section></div>
}
