'use client'

import QRCode from 'qrcode'
import { useCallback, useEffect, useMemo, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { ActorState } from '../../chat-interface/auth'
import {
  buildBindingOwnerRows,
  filterBindingsForAdminOverview,
  getChannelManagementQrRenderState,
  mergeGeneratedQrcodes,
  normalizeBindingOwnerUserId,
  selectBindingsByChannelPage,
} from '../../chat-interface/channelManagement'
import {
  CHANNEL_BINDINGS_API_PATH,
  FEISHU_BINDING_API_PATH,
  FEISHU_BINDINGS_API_PATH,
  WEIXIN_BINDING_API_PATH,
  WEIXIN_BINDING_QRCODE_API_PATH,
  WEIXIN_BINDING_QRCODE_STATUS_API_PATH,
  WEIXIN_BINDINGS_API_PATH,
} from '../../chat-interface/constants'
import type {
  ChannelManagementPage,
  ChannelBindingListResponse,
  ChannelBindingRecord,
  WeixinClawBotQrcodeStatusResponse,
} from '../../chat-interface/types'
import { formatDateTime } from '../../chat-interface/utils'

interface ChannelManagementViewProps {
  actor: ActorState
  userId: string
  channelPage: ChannelManagementPage
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
}

type ChannelScope = 'my' | 'all'

function buildBindingsPath(scope: ChannelScope): string {
  return `${CHANNEL_BINDINGS_API_PATH}?scope=${scope}`
}

function getBindingRuntimeStatus(binding: ChannelBindingRecord): string {
  return String(binding.runtime_state?.status || binding.status || 'pending')
}

function isDirectImageUrl(value: string): boolean {
  const normalized = value.toLowerCase()
  return (
    normalized.startsWith('data:image/') ||
    normalized.endsWith('.png') ||
    normalized.endsWith('.jpg') ||
    normalized.endsWith('.jpeg') ||
    normalized.endsWith('.gif') ||
    normalized.endsWith('.webp') ||
    normalized.endsWith('.svg')
  )
}

function getBindingQrcodeUrl(binding: ChannelBindingRecord): string {
  const runtimeState = binding.runtime_state || {}
  const qrcodeUrl = runtimeState.qrcode_url
  const qrcode = runtimeState.qrcode
  if (typeof qrcodeUrl === 'string' && qrcodeUrl.trim()) return qrcodeUrl
  if (
    typeof qrcode === 'string' &&
    (qrcode.startsWith('http://') || qrcode.startsWith('https://'))
  ) {
    return qrcode
  }
  return ''
}

function getBindingQrcodePayload(binding: ChannelBindingRecord): string {
  const runtimeState = binding.runtime_state || {}
  const qrcode = runtimeState.qrcode
  return typeof qrcode === 'string' ? qrcode : ''
}

function maskText(value: string, head = 4, tail = 3): string {
  if (value.length <= head + tail) return value
  return `${value.slice(0, head)}***${value.slice(-tail)}`
}

export function ChannelManagementView({
  actor,
  userId,
  channelPage,
  requestJson,
}: ChannelManagementViewProps) {
  const [scope, setScope] = useState<ChannelScope>('my')
  const [bindings, setBindings] = useState<ChannelBindingRecord[]>([])
  const [loadingBindings, setLoadingBindings] = useState(false)
  const [submittingWeixin, setSubmittingWeixin] = useState(false)
  const [submittingFeishu, setSubmittingFeishu] = useState(false)
  const [pendingBindingId, setPendingBindingId] = useState<number | null>(null)
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [bindingSearch, setBindingSearch] = useState('')

  const [weixinDisplayName, setWeixinDisplayName] = useState('')
  const [weixinOwnerUserId, setWeixinOwnerUserId] = useState(userId)
  const [feishuDisplayName, setFeishuDisplayName] = useState('')
  const [feishuOwnerUserId, setFeishuOwnerUserId] = useState(userId)
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuAppSecret, setFeishuAppSecret] = useState('')
  const [feishuDomain, setFeishuDomain] = useState<'feishu' | 'lark'>('feishu')
  const [feishuGroupPolicy, setFeishuGroupPolicy] = useState<'mention' | 'open'>(
    'mention'
  )
  const [feishuStreaming, setFeishuStreaming] = useState(true)
  const [adminOwnerFilter, setAdminOwnerFilter] = useState('')
  const [adminStatusFilter, setAdminStatusFilter] = useState('')
  const [statusOverrides, setStatusOverrides] = useState<
    Record<number, WeixinClawBotQrcodeStatusResponse>
  >({})
  const [generatedQrcodes, setGeneratedQrcodes] = useState<Record<number, string>>({})

  const canViewAdminScope = actor.role === 'admin'

  useEffect(() => {
    if (!createOpen) return
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setCreateOpen(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [createOpen])

  const loadBindings = useCallback(
    async (nextScope: ChannelScope = scope) => {
      setLoadingBindings(true)
      setError('')
      try {
        const response = await requestJson<ChannelBindingListResponse>(
          buildBindingsPath(nextScope)
        )
        setBindings(response.items)
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError))
      } finally {
        setLoadingBindings(false)
      }
    },
    [requestJson, scope]
  )

  useEffect(() => {
    void loadBindings(scope)
  }, [loadBindings, scope])

  useEffect(() => {
    setWeixinOwnerUserId(userId)
    setFeishuOwnerUserId(userId)
  }, [userId])

  useEffect(() => {
    let cancelled = false
    const weixinBindings = bindings.filter((binding) => binding.channel === 'weixin_clawbot')

    async function generate() {
      const nextMap: Record<number, string> = {}
      for (const binding of weixinBindings) {
        const qrcodeUrl = getBindingQrcodeUrl(binding)
        const payload = getBindingQrcodePayload(binding)
        const renderState = getChannelManagementQrRenderState({
          qrcode: payload,
          qrcodeUrl,
          generatedDataUrl: generatedQrcodes[binding.id] || '',
        })
        if (!renderState.shouldGenerateDataUrl || !renderState.payload) continue
        try {
          nextMap[binding.id] = await QRCode.toDataURL(renderState.payload, {
            errorCorrectionLevel: 'M',
            margin: 2,
            width: 220,
          })
        } catch {
          nextMap[binding.id] = ''
        }
      }
      if (!cancelled && Object.keys(nextMap).length > 0) {
        setGeneratedQrcodes((current) => mergeGeneratedQrcodes(current, nextMap))
      }
    }

    void generate()
    return () => {
      cancelled = true
    }
  }, [bindings, generatedQrcodes])

  const currentChannel = channelPage === 'feishu' ? 'feishu' : 'weixin_clawbot'
  const currentChannelLabel = currentChannel === 'feishu' ? '飞书' : '微信'

  const visibleBindings = useMemo(() => {
    if (scope !== 'all') {
      return selectBindingsByChannelPage(bindings, channelPage)
    }
    return filterBindingsForAdminOverview(bindings, {
      ownerUserId: adminOwnerFilter.trim(),
      channel: currentChannel,
      status: adminStatusFilter.trim(),
    })
  }, [
    adminOwnerFilter,
    adminStatusFilter,
    bindings,
    channelPage,
    currentChannel,
    scope,
  ])

  const channelBindings = visibleBindings
  const filteredBindings = useMemo(() => {
    const query = bindingSearch.trim().toLocaleLowerCase()
    if (!query) return channelBindings
    return channelBindings.filter((binding) =>
      [binding.display_name, binding.owner_user_id, binding.manager_user_id]
        .some((value) => String(value || '').toLocaleLowerCase().includes(query))
    )
  }, [bindingSearch, channelBindings])
  const ownerRows = useMemo(
    () => buildBindingOwnerRows(filteredBindings),
    [filteredBindings]
  )
  const selectedBinding = useMemo(
    () => filteredBindings.find((binding) => binding.id === selectedBindingId) || filteredBindings[0] || null,
    [filteredBindings, selectedBindingId]
  )

  useEffect(() => {
    if (!filteredBindings.some((binding) => binding.id === selectedBindingId)) {
      setSelectedBindingId(filteredBindings[0]?.id ?? null)
    }
  }, [filteredBindings, selectedBindingId])

  const createWeixinBinding = useCallback(async () => {
    const displayName = weixinDisplayName.trim()
    const ownerUserId = normalizeBindingOwnerUserId(weixinOwnerUserId, userId)
    if (!displayName) {
      setError('请先输入微信绑定备注名。')
      return
    }

    setSubmittingWeixin(true)
    setError('')
    setNotice('')
    try {
      const response = await requestJson<ChannelBindingRecord & { qrcode_url?: string }>(
        WEIXIN_BINDINGS_API_PATH,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            owner_user_id: ownerUserId,
            display_name: displayName,
          }),
        }
      )
      setWeixinDisplayName('')
      setCreateOpen(false)
      setNotice(`微信绑定 ${response.display_name || displayName} 已创建，请扫码登录。`)
      await loadBindings(scope)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setSubmittingWeixin(false)
    }
  }, [loadBindings, requestJson, scope, userId, weixinDisplayName, weixinOwnerUserId])

  const createFeishuBinding = useCallback(async () => {
    const displayName = feishuDisplayName.trim()
    const ownerUserId = normalizeBindingOwnerUserId(feishuOwnerUserId, userId)
    if (!displayName || !feishuAppId.trim() || !feishuAppSecret.trim()) {
      setError('请完整填写飞书备注名、App ID 和 App Secret。')
      return
    }

    setSubmittingFeishu(true)
    setError('')
    setNotice('')
    try {
      const response = await requestJson<ChannelBindingRecord>(FEISHU_BINDINGS_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner_user_id: ownerUserId,
          display_name: displayName,
          app_id: feishuAppId.trim(),
          app_secret: feishuAppSecret.trim(),
          domain: feishuDomain,
          group_policy: feishuGroupPolicy,
          streaming: feishuStreaming,
        }),
      })
      setFeishuDisplayName('')
      setFeishuAppId('')
      setFeishuAppSecret('')
      setCreateOpen(false)
      setNotice(`飞书绑定 ${response.display_name || displayName} 已创建。`)
      await loadBindings(scope)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setSubmittingFeishu(false)
    }
  }, [
    feishuAppId,
    feishuAppSecret,
    feishuDisplayName,
    feishuDomain,
    feishuGroupPolicy,
    feishuOwnerUserId,
    feishuStreaming,
    loadBindings,
    requestJson,
    scope,
    userId,
  ])

  const refreshWeixinQrcode = useCallback(
    async (bindingId: number) => {
      setPendingBindingId(bindingId)
      setError('')
      setNotice('')
      try {
        const response = await requestJson<ChannelBindingRecord & { qrcode_url?: string }>(
          WEIXIN_BINDING_QRCODE_API_PATH(bindingId),
          { method: 'POST' }
        )
        setNotice(`微信绑定 ${response.display_name || bindingId} 的二维码已刷新。`)
        await loadBindings(scope)
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError))
      } finally {
        setPendingBindingId(null)
      }
    },
    [loadBindings, requestJson, scope]
  )

  const checkWeixinStatus = useCallback(
    async (bindingId: number) => {
      setPendingBindingId(bindingId)
      setError('')
      try {
        const response = await requestJson<WeixinClawBotQrcodeStatusResponse>(
          WEIXIN_BINDING_QRCODE_STATUS_API_PATH(bindingId)
        )
        setStatusOverrides((current) => ({ ...current, [bindingId]: response }))
        setNotice(
          response.bot_token
            ? `微信绑定 ${bindingId} 已扫码确认。`
            : `微信绑定 ${bindingId} 当前状态：${response.status || 'pending'}`
        )
        await loadBindings(scope)
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError))
      } finally {
        setPendingBindingId(null)
      }
    },
    [loadBindings, requestJson, scope]
  )

  const deleteBinding = useCallback(
    async (binding: ChannelBindingRecord) => {
      if (
        typeof window !== 'undefined' &&
        !window.confirm(`确认删除绑定 ${binding.display_name || binding.id} 吗？`)
      ) {
        return
      }

      setPendingBindingId(binding.id)
      setError('')
      setNotice('')
      try {
        await requestJson<{ deleted: boolean }>(
          binding.channel === 'feishu'
            ? FEISHU_BINDING_API_PATH(binding.id)
            : WEIXIN_BINDING_API_PATH(binding.id),
          { method: 'DELETE' }
        )
        setNotice(`绑定 ${binding.display_name || binding.id} 已删除。`)
        await loadBindings(scope)
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : String(nextError))
      } finally {
        setPendingBindingId(null)
      }
    },
    [loadBindings, requestJson, scope]
  )

  const currentPageTitle =
    channelPage === 'feishu' ? '飞书绑定管理' : '微信绑定管理'
  const currentPageDescription =
    channelPage === 'feishu'
      ? '集中管理飞书绑定的配置、状态、归属用户和删除。'
      : '集中管理微信绑定的扫码、状态检查、归属用户和删除。'
  const selectedStatus = selectedBinding
    ? statusOverrides[selectedBinding.id]?.status || getBindingRuntimeStatus(selectedBinding)
    : ''
  const selectedQr = selectedBinding && channelPage === 'weixin'
    ? getChannelManagementQrRenderState({
        qrcode: getBindingQrcodePayload(selectedBinding),
        qrcodeUrl: getBindingQrcodeUrl(selectedBinding),
        generatedDataUrl: generatedQrcodes[selectedBinding.id] || '',
      })
    : null
  const ownerListSection = (
    <section className={styles.channelListPanel} aria-label="绑定列表" aria-busy={loadingBindings}>
      <div className={styles.channelPanelHeading}><strong>绑定列表</strong><span>{filteredBindings.length} 条 · {ownerRows.length} 个用户</span></div>
      <div>
        {ownerRows.length === 0 ? (
          <div className={styles.extensionEmpty}><strong>没有匹配的绑定</strong><span>可调整筛选条件，或新增一个{currentChannelLabel}绑定。</span></div>
        ) : (
          ownerRows.map((row) => (
            <div key={row.ownerUserId} className={styles.channelOwnerGroup}>
              <div className={styles.channelOwnerHeading}><strong>{row.ownerUserId}</strong><span>{row.total} 条 · {row.summary.connected} 在线</span></div>
              {filteredBindings.filter((binding) => binding.owner_user_id === row.ownerUserId).map((binding) => {
                const status = statusOverrides[binding.id]?.status || getBindingRuntimeStatus(binding)
                return (
                  <button type="button" key={binding.id} className={`${styles.channelBindingRow} ${selectedBinding?.id === binding.id ? styles.channelBindingRowActive : ''}`} onClick={() => setSelectedBindingId(binding.id)} aria-current={selectedBinding?.id === binding.id ? 'true' : undefined}>
                    <span className={styles.channelBindingIcon} aria-hidden="true">{currentChannelLabel.slice(0, 1)}</span>
                    <span className={styles.channelBindingIdentity}><strong>{binding.display_name || `绑定 ${binding.id}`}</strong><small>#{binding.id} · {formatDateTime(binding.updated_at)}</small></span>
                    <span className={`${styles.channelStatus} ${status === 'connected' ? styles.channelStatusConnected : status === 'error' ? styles.channelStatusError : ''}`}>{status}</span>
                  </button>
                )
              })}
            </div>
          ))
        )}
      </div>
    </section>
  )

  return (
    <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace} ${styles.channelWorkspace}`}>
      <header className={styles.extensionHeading}>
        <div>
          <span className={styles.extensionEyebrow}>CONNECTIONS / {channelPage === 'weixin' ? 'WECHAT' : 'FEISHU'}</span>
          <h2>{currentPageTitle}</h2>
          <p>{currentPageDescription}</p>
        </div>
        <div className={styles.extensionHeadingActions}>
          <span className={styles.extensionCount}>{channelBindings.length} 条绑定</span>
          <button type="button" className={styles.extensionSecondaryButton} disabled={loadingBindings} onClick={() => void loadBindings(scope)}>
            {loadingBindings ? '刷新中…' : '刷新'}
          </button>
          <button type="button" className={styles.extensionPrimaryButton} onClick={() => setCreateOpen(true)}>＋ 新增绑定</button>
        </div>
      </header>

      <div className={styles.channelToolbar}>
        <div className={styles.channelScope} role="group" aria-label="绑定查看范围">
          <button
            className={
              scope === 'my' ? styles.channelScopeActive : ''
            }
            onClick={() => setScope('my')}
          >
            我的绑定
          </button>
          {canViewAdminScope ? (
            <button
              className={
                scope === 'all'
                  ? styles.channelScopeActive
                  : ''
              }
              onClick={() => setScope('all')}
            >
              全部绑定
            </button>
          ) : null}
        </div>
        <div className={styles.channelFilters}>
          {scope === 'all' && <>
            <input className={styles.channelFilterInput} value={adminOwnerFilter} onChange={(event) => setAdminOwnerFilter(event.target.value)} placeholder="所属用户 ID" aria-label="筛选所属用户" />
            <select className={styles.channelFilterInput} value={adminStatusFilter} onChange={(event) => setAdminStatusFilter(event.target.value)} aria-label="筛选运行状态">
              <option value="">全部状态</option><option value="connected">已连接</option><option value="pending">待处理</option><option value="error">异常</option><option value="starting">启动中</option><option value="stopped">已停止</option>
            </select>
          </>}
          <label className={styles.extensionSearch}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
            <input value={bindingSearch} onChange={(event) => setBindingSearch(event.target.value)} placeholder="搜索绑定" aria-label="搜索绑定" />
          </label>
        </div>
      </div>

      <div className={styles.managementNoticeRow}>
        {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
        {error ? <div className={styles.managementError}>{error}</div> : null}
      </div>

      {createOpen && (
        <div className={styles.extensionDialogOverlay} onMouseDown={(event) => { if (event.target === event.currentTarget) setCreateOpen(false) }}>
          <section className={`${styles.extensionDialog} ${styles.channelCreateDialog}`} role="dialog" aria-modal="true" aria-labelledby="channel-create-title">
            <div className={styles.extensionDialogHeader}><div><span className={styles.extensionEyebrow}>NEW / {currentChannelLabel}</span><h3 id="channel-create-title">新增{currentChannelLabel}绑定</h3></div><button type="button" className={styles.extensionIconButton} aria-label="关闭新增绑定" onClick={() => setCreateOpen(false)}>×</button></div>
            <div className={styles.channelCreateFields}>
              <label>所属系统用户 ID<input className={styles.managementInput} value={channelPage === 'weixin' ? weixinOwnerUserId : feishuOwnerUserId} onChange={(event) => channelPage === 'weixin' ? setWeixinOwnerUserId(event.target.value) : setFeishuOwnerUserId(event.target.value)} /></label>
              <label>绑定备注名<input className={styles.managementInput} value={channelPage === 'weixin' ? weixinDisplayName : feishuDisplayName} onChange={(event) => channelPage === 'weixin' ? setWeixinDisplayName(event.target.value) : setFeishuDisplayName(event.target.value)} placeholder="便于识别的名称" /></label>
              {channelPage === 'feishu' && <>
                <label>App ID<input className={styles.managementInput} value={feishuAppId} onChange={(event) => setFeishuAppId(event.target.value)} /></label>
                <label>App Secret<input type="password" className={styles.managementInput} value={feishuAppSecret} onChange={(event) => setFeishuAppSecret(event.target.value)} autoComplete="off" /></label>
                <label>应用域名<select className={styles.managementInput} value={feishuDomain} onChange={(event) => setFeishuDomain(event.target.value as 'feishu' | 'lark')}><option value="feishu">Feishu</option><option value="lark">Lark</option></select></label>
                <label>群聊策略<select className={styles.managementInput} value={feishuGroupPolicy} onChange={(event) => setFeishuGroupPolicy(event.target.value as 'mention' | 'open')}><option value="mention">仅被提及时回复</option><option value="open">开放回复</option></select></label>
                <label className={styles.channelCreateSwitch}>长连接<button type="button" role="switch" aria-checked={feishuStreaming} className={`${styles.extensionSwitch} ${feishuStreaming ? styles.extensionSwitchOn : ''}`} onClick={() => setFeishuStreaming((current) => !current)}><span /></button></label>
              </>}
            </div>
            {error && <div className={styles.managementError} role="alert">{error}</div>}
            <div className={styles.extensionDialogActions}><button type="button" className={styles.extensionSecondaryButton} onClick={() => setCreateOpen(false)}>取消</button><button type="button" className={styles.extensionPrimaryButton} disabled={submittingWeixin || submittingFeishu} onClick={() => void (channelPage === 'weixin' ? createWeixinBinding() : createFeishuBinding())}>{submittingWeixin || submittingFeishu ? '创建中…' : '创建绑定'}</button></div>
          </section>
        </div>
      )}

      <div className={styles.channelWorkspaceGrid}>
        {ownerListSection}
        <section className={styles.channelDetailPanel} aria-label="绑定详情">
          {!selectedBinding ? (
            <div className={styles.extensionEmpty}><strong>选择绑定查看详情</strong><span>选中左侧记录后，可检查状态和管理配置。</span></div>
          ) : (
            <>
              <div className={styles.channelDetailHeading}>
                <div><span className={styles.extensionEyebrow}>BINDING / {selectedBinding.id}</span><h3>{selectedBinding.display_name || `绑定 ${selectedBinding.id}`}</h3><span className={styles.channelDetailSubtitle}>所属用户 {selectedBinding.owner_user_id} · 管理人 {selectedBinding.manager_user_id}</span></div>
                <span className={`${styles.channelStatus} ${selectedStatus === 'connected' ? styles.channelStatusConnected : selectedStatus === 'error' ? styles.channelStatusError : ''}`}>{selectedStatus}</span>
              </div>
              {channelPage === 'weixin' ? (
                <div className={styles.channelSection}>
                  <h4>扫码登录</h4>
                  <div className={styles.channelQrContent}>
                    {selectedQr?.imageSrc ? <img className={styles.channelQrImage} src={isDirectImageUrl(selectedQr.imageSrc) ? selectedQr.imageSrc : generatedQrcodes[selectedBinding.id] || selectedQr.imageSrc} alt={`${selectedBinding.display_name || selectedBinding.id} 二维码`} /> : <div className={styles.channelQrPlaceholder}>等待生成二维码</div>}
                    <div className={styles.channelQrCopy}>
                      <strong>使用微信扫码</strong><p>二维码失效时刷新，扫码后检查连接状态。</p>
                      <div className={styles.channelDetailActions}>
                        <button className={styles.extensionSecondaryButton} disabled={pendingBindingId === selectedBinding.id} onClick={() => void checkWeixinStatus(selectedBinding.id)}>{pendingBindingId === selectedBinding.id ? '检查中…' : '检查状态'}</button>
                        <button className={styles.extensionSecondaryButton} disabled={pendingBindingId === selectedBinding.id} onClick={() => void refreshWeixinQrcode(selectedBinding.id)}>刷新二维码</button>
                      </div>
                      {getBindingQrcodeUrl(selectedBinding) && <a className={styles.channelExternalLink} href={getBindingQrcodeUrl(selectedBinding)} target="_blank" rel="noreferrer">在新窗口打开二维码链接 ↗</a>}
                    </div>
                  </div>
                </div>
              ) : (
                <div className={styles.channelSection}>
                  <h4>飞书应用配置</h4>
                  <dl className={styles.channelDetailTable}>
                    <div><dt>App ID</dt><dd>{typeof selectedBinding.credentials.app_id === 'string' ? maskText(selectedBinding.credentials.app_id) : '未配置'}</dd></div>
                    <div><dt>群聊策略</dt><dd>{typeof selectedBinding.config.group_policy === 'string' ? selectedBinding.config.group_policy : 'mention'}</dd></div>
                    <div><dt>Bot Open ID</dt><dd>{typeof selectedBinding.runtime_state.bot_open_id === 'string' ? selectedBinding.runtime_state.bot_open_id : '未识别'}</dd></div>
                  </dl>
                </div>
              )}
              <div className={styles.channelSection}>
                <h4>绑定信息</h4>
                <dl className={styles.channelDetailTable}>
                  <div><dt>所属用户</dt><dd>{selectedBinding.owner_user_id}</dd></div>
                  <div><dt>管理人</dt><dd>{selectedBinding.manager_user_id}</dd></div>
                  {channelPage === 'weixin' && <div><dt>ClawBot 节点</dt><dd>{typeof selectedBinding.credentials.base_url === 'string' ? selectedBinding.credentials.base_url : statusOverrides[selectedBinding.id]?.base_url || statusOverrides[selectedBinding.id]?.baseurl || '未获取'}</dd></div>}
                  <div><dt>最近更新</dt><dd>{formatDateTime(selectedBinding.updated_at)}</dd></div>
                </dl>
              </div>
              <div className={styles.channelDangerZone}><button type="button" className={styles.extensionDeleteButton} disabled={pendingBindingId === selectedBinding.id} onClick={() => void deleteBinding(selectedBinding)}>删除绑定</button></div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
