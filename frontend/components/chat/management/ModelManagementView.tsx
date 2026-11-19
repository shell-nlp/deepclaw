'use client'

import { useCallback, useEffect, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import { MODEL_CONFIG_API_PATH } from '../utils/constants'
import type { ActorState } from '../utils/auth'

interface ModelConfig { api_base: string; api_key_masked: string; has_api_key: boolean; chat_model_name: string; embedding_model_name: string; model_context_window: number; source: 'saved' | 'environment' }
interface ModelManagementViewProps { actor: ActorState; requestJson: <T>(path: string, init?: RequestInit) => Promise<T> }

/** 管理 OpenAI 兼容网关、聊天模型和向量模型配置。
 * Args:
 *   actor: 当前登录主体。
 *   requestJson: 带鉴权的 JSON 请求函数。
 */
export function ModelManagementView({ actor, requestJson }: ModelManagementViewProps) {
  const [config, setConfig] = useState<ModelConfig | null>(null)
  const [apiBase, setApiBase] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [chatModel, setChatModel] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [contextWindow, setContextWindow] = useState('128000')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const next = await requestJson<ModelConfig>(MODEL_CONFIG_API_PATH)
      setConfig(next); setApiBase(next.api_base); setChatModel(next.chat_model_name); setEmbeddingModel(next.embedding_model_name); setContextWindow(String(next.model_context_window))
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法读取模型配置。') }
    finally { setLoading(false) }
  }, [requestJson])

  useEffect(() => { if (actor.role === 'admin' && !actor.isGuest) void load() }, [actor.isGuest, actor.role, load])

  if (actor.isGuest || actor.role !== 'admin') return (
    <div className={styles.managementPage}><div className={styles.managementTopbar}><div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 模型管理</span><h2>模型管理</h2><p>模型连接属于系统级配置，仅管理员可以查看和修改。</p></div></div><div className={styles.managementPageGrid}><section className={styles.managementCard}><div className={styles.managementHeader}><h3>需要管理员权限</h3><span className={styles.accountRoleBadge}>{actor.isGuest ? '游客' : '普通用户'}</span></div><p className={styles.managementDescription}>登录管理员账号后，可以在这里切换 OpenAI 兼容网关、聊天模型和向量模型。密钥只在服务端保存，页面不会回显原文。</p></section></div></div>
  )

  const save = async () => {
    setSaving(true); setNotice(''); setError('')
    try {
      const next = await requestJson<ModelConfig>(MODEL_CONFIG_API_PATH, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_base: apiBase.trim(), api_key: apiKey.trim() || null, chat_model_name: chatModel.trim(), embedding_model_name: embeddingModel.trim(), model_context_window: Number(contextWindow) }) })
      setConfig(next); setApiKey(''); setNotice('模型配置已保存，新的对话会使用最新配置。')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存模型配置失败。') }
    finally { setSaving(false) }
  }

  return <div className={styles.managementPage}>
    <div className={styles.managementNoticeRow}>{notice ? <div className={styles.managementNotice} role="status">{notice}</div> : null}{error ? <div className={styles.managementError} role="alert">{error}</div> : null}</div>
    <div className={styles.managementTopbar}><div className={styles.managementRouteInfo}><span className={styles.managementBreadcrumb}>系统 / 模型管理</span><h2>模型管理</h2><p>把模型网关从环境变量带进控制面，统一管理聊天、向量和上下文窗口。</p></div><div className={styles.managementTopbarMeta}><span className={styles.managementMeta}>{loading ? '读取中…' : config?.source === 'saved' ? '已保存配置' : '环境变量配置'}</span></div></div>
    <div className={styles.managementPageGrid}>
      <section className={styles.managementCard}><div className={styles.managementHeader}><div><h3>连接入口</h3><p className={styles.managementDescription}>兼容 OpenAI API 的服务地址，末尾不需要补 chat/completions。</p></div><span className={styles.accountRoleBadge}>Gateway</span></div><div className={styles.managementForm}><label className={styles.managementField}><span>API Base URL</span><input className={styles.managementInput} value={apiBase} onChange={(event) => setApiBase(event.target.value)} placeholder="https://api.example.com/v1" /></label><label className={styles.managementField}><span>API Key</span><input className={styles.managementInput} type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={config?.has_api_key ? '已配置密钥 · 留空保持不变' : '输入服务密钥'} autoComplete="new-password" /></label></div></section>
      <section className={styles.managementCard}><div className={styles.managementHeader}><div><h3>模型角色</h3><p className={styles.managementDescription}>聊天模型负责推理与工具调用，向量模型负责知识库索引与检索。</p></div><span className={styles.accountRoleBadge}>Runtime</span></div><div className={styles.managementForm}><label className={styles.managementField}><span>聊天模型</span><input className={styles.managementInput} value={chatModel} onChange={(event) => setChatModel(event.target.value)} placeholder="deepseek-chat" /></label><label className={styles.managementField}><span>向量模型</span><input className={styles.managementInput} value={embeddingModel} onChange={(event) => setEmbeddingModel(event.target.value)} placeholder="text-embedding-3-small" /></label><label className={styles.managementField}><span>上下文窗口</span><input className={styles.managementInput} type="number" min="1" value={contextWindow} onChange={(event) => setContextWindow(event.target.value)} /></label></div><div className={styles.managementToolbar}><button type="button" className={styles.managementButton} onClick={() => void save()} disabled={saving || loading}>{saving ? '保存中…' : '保存模型配置'}</button><span className={styles.managementMeta}>保存后会清理智能体缓存，新请求使用新模型。</span></div></section>
    </div>
  </div>
}
