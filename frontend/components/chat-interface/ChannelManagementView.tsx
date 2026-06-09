'use client'

import QRCode from 'qrcode'
import { useCallback, useEffect, useMemo, useState } from 'react'

import styles from '../ChatInterface.module.css'
import type { ActorState } from './auth'
import {
  filterBindingsForAdminOverview,
  getChannelManagementQrRenderState,
  groupBindingsByChannel,
  mergeGeneratedQrcodes,
  normalizeBindingOwnerUserId,
  summarizeChannelBindings,
} from './channelManagement'
import {
  CHANNEL_BINDINGS_API_PATH,
  FEISHU_BINDING_API_PATH,
  FEISHU_BINDINGS_API_PATH,
  WEIXIN_BINDING_API_PATH,
  WEIXIN_BINDING_QRCODE_API_PATH,
  WEIXIN_BINDING_QRCODE_STATUS_API_PATH,
  WEIXIN_BINDINGS_API_PATH,
} from './constants'
import type {
  ChannelBindingListResponse,
  ChannelBindingRecord,
  WeixinClawBotQrcodeStatusResponse,
} from './types'
import { formatDateTime } from './utils'

interface ChannelManagementViewProps {
  actor: ActorState
  userId: string
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

function getChannelLabel(channel: string): string {
  if (channel === 'weixin_clawbot') return '微信'
  if (channel === 'feishu') return '飞书'
  return channel
}

export function ChannelManagementView({
  actor,
  userId,
  requestJson,
}: ChannelManagementViewProps) {
  const [scope, setScope] = useState<ChannelScope>('my')
  const [bindings, setBindings] = useState<ChannelBindingRecord[]>([])
  const [loadingBindings, setLoadingBindings] = useState(false)
  const [submittingWeixin, setSubmittingWeixin] = useState(false)
  const [submittingFeishu, setSubmittingFeishu] = useState(false)
  const [pendingBindingId, setPendingBindingId] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

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
  const [adminChannelFilter, setAdminChannelFilter] = useState('')
  const [adminStatusFilter, setAdminStatusFilter] = useState('')
  const [statusOverrides, setStatusOverrides] = useState<
    Record<number, WeixinClawBotQrcodeStatusResponse>
  >({})
  const [generatedQrcodes, setGeneratedQrcodes] = useState<Record<number, string>>({})

  const canViewAdminScope = actor.role === 'admin'

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

  const visibleBindings = useMemo(() => {
    if (scope !== 'all') return bindings
    return filterBindingsForAdminOverview(bindings, {
      ownerUserId: adminOwnerFilter.trim(),
      channel: adminChannelFilter.trim(),
      status: adminStatusFilter.trim(),
    })
  }, [adminChannelFilter, adminOwnerFilter, adminStatusFilter, bindings, scope])

  const groupedBindings = useMemo(
    () => groupBindingsByChannel(visibleBindings),
    [visibleBindings]
  )
  const weixinBindings = groupedBindings.weixin_clawbot || []
  const feishuBindings = groupedBindings.feishu || []
  const allChannels = Object.keys(groupedBindings)

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

  return (
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>Channel Management</span>
          <h2>统一绑定中心</h2>
          <p>
            在这里集中管理当前系统用户名下的微信与飞书绑定。管理员可以切换到全局总览，
            查看所有用户的绑定状态并执行删除。
          </p>
        </div>
        <div className={styles.managementHeroActions}>
          <button
            className={
              scope === 'my' ? styles.managementButton : styles.managementMinorButton
            }
            onClick={() => setScope('my')}
          >
            我的绑定
          </button>
          {canViewAdminScope ? (
            <button
              className={
                scope === 'all'
                  ? styles.managementButton
                  : styles.managementMinorButton
              }
              onClick={() => setScope('all')}
            >
              管理员总览
            </button>
          ) : null}
          <button
            className={styles.managementMinorButton}
            disabled={loadingBindings}
            onClick={() => void loadBindings(scope)}
          >
            {loadingBindings ? '刷新中...' : '刷新列表'}
          </button>
        </div>
      </section>

      <div className={styles.managementNoticeRow}>
        {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
        {error ? <div className={styles.managementError}>{error}</div> : null}
      </div>

      <div className={styles.managementSummaryGrid}>
        {allChannels.length === 0 ? (
          <div className={styles.managementSummaryCard}>
            <span className={styles.managementSummaryLabel}>当前绑定</span>
            <strong className={styles.managementSummaryValue}>0</strong>
            <span className={styles.managementMeta}>还没有任何渠道绑定</span>
          </div>
        ) : (
          allChannels.map((channel) => {
            const summary = summarizeChannelBindings(groupedBindings[channel] || [])
            return (
              <div key={channel} className={styles.managementSummaryCard}>
                <span className={styles.managementSummaryLabel}>
                  {getChannelLabel(channel)}
                </span>
                <strong className={styles.managementSummaryValue}>{summary.total}</strong>
                <span className={styles.managementMeta}>
                  在线 {summary.connected} / 待处理 {summary.pending} / 异常{' '}
                  {summary.error}
                </span>
              </div>
            )
          })
        )}
      </div>

      {scope === 'all' ? (
        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>管理员总览</h3>
            <span className={styles.managementMeta}>
              {visibleBindings.length} 条绑定
            </span>
          </div>
          <div className={styles.managementToolbar}>
            <input
              className={styles.managementInput}
              value={adminOwnerFilter}
              onChange={(event) => setAdminOwnerFilter(event.target.value)}
              placeholder="按所属系统用户筛选"
            />
            <select
              className={styles.managementInput}
              value={adminChannelFilter}
              onChange={(event) => setAdminChannelFilter(event.target.value)}
            >
              <option value="">全部渠道</option>
              <option value="weixin_clawbot">微信</option>
              <option value="feishu">飞书</option>
            </select>
            <select
              className={styles.managementInput}
              value={adminStatusFilter}
              onChange={(event) => setAdminStatusFilter(event.target.value)}
            >
              <option value="">全部状态</option>
              <option value="connected">connected</option>
              <option value="pending">pending</option>
              <option value="error">error</option>
              <option value="starting">starting</option>
              <option value="stopped">stopped</option>
            </select>
          </div>
          <div className={styles.managementList}>
            {visibleBindings.length === 0 ? (
              <div className={styles.managementEmpty}>当前没有匹配的绑定记录。</div>
            ) : (
              visibleBindings.map((binding) => (
                <div key={binding.id} className={styles.managementListItemStatic}>
                  <div className={styles.managementListHeader}>
                    <strong>{binding.display_name || `绑定 ${binding.id}`}</strong>
                    <span>{getBindingRuntimeStatus(binding)}</span>
                  </div>
                  <p className={styles.managementDescription}>
                    所属用户 {binding.owner_user_id} / 渠道 {getChannelLabel(binding.channel)}
                  </p>
                  <div className={styles.managementListMeta}>
                    <span>管理人: {binding.manager_user_id}</span>
                    <span>更新时间: {formatDateTime(binding.updated_at)}</span>
                  </div>
                  <div className={styles.managementActionRow}>
                    <button
                      className={styles.managementDangerMinorButton}
                      disabled={pendingBindingId === binding.id}
                      onClick={() => void deleteBinding(binding)}
                    >
                      {pendingBindingId === binding.id ? '删除中...' : '删除绑定'}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      ) : (
        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>微信绑定</h3>
              <span className={styles.managementMeta}>{weixinBindings.length} 条</span>
            </div>
            <div className={styles.managementToolbar}>
              <input
                className={styles.managementInput}
                value={weixinOwnerUserId}
                onChange={(event) => setWeixinOwnerUserId(event.target.value)}
                placeholder="所属系统用户 ID"
              />
              <input
                className={styles.managementInput}
                value={weixinDisplayName}
                onChange={(event) => setWeixinDisplayName(event.target.value)}
                placeholder="例如：张三主号 / 李四代绑号"
              />
              <button
                className={styles.managementButton}
                disabled={submittingWeixin}
                onClick={() => void createWeixinBinding()}
              >
                {submittingWeixin ? '创建中...' : '新增微信绑定'}
              </button>
            </div>
            <div className={styles.managementMetaPanel}>
              <span>同一系统用户可以维护多个微信绑定。</span>
              <span>每条绑定独立生成二维码、独立维护状态、独立删除。</span>
            </div>
            <div className={styles.managementList}>
              {weixinBindings.length === 0 ? (
                <div className={styles.managementEmpty}>当前还没有微信绑定。</div>
              ) : (
                weixinBindings.map((binding) => {
                  const status = statusOverrides[binding.id]
                  const qrcodeUrl = getBindingQrcodeUrl(binding)
                  const qrcodePayload = getBindingQrcodePayload(binding)
                  const renderState = getChannelManagementQrRenderState({
                    qrcode: qrcodePayload,
                    qrcodeUrl,
                    generatedDataUrl: generatedQrcodes[binding.id] || '',
                  })
                  const baseUrl =
                    typeof binding.credentials.base_url === 'string'
                      ? binding.credentials.base_url
                      : status?.base_url || status?.baseurl || '未获取'

                  return (
                    <div key={binding.id} className={styles.managementListItemStatic}>
                      <div className={styles.managementListHeader}>
                        <strong>{binding.display_name || `绑定 ${binding.id}`}</strong>
                        <span>{status?.status || getBindingRuntimeStatus(binding)}</span>
                      </div>
                      <div className={styles.channelQrPanel}>
                        {renderState.imageSrc ? (
                          <img
                            className={styles.channelQrImage}
                            src={
                              isDirectImageUrl(renderState.imageSrc)
                                ? renderState.imageSrc
                                : generatedQrcodes[binding.id] || renderState.imageSrc
                            }
                            alt={`${binding.display_name || binding.id} 二维码`}
                          />
                        ) : (
                          <div className={styles.channelQrPlaceholder}>等待生成二维码</div>
                        )}
                        <div className={styles.channelQrDetails}>
                          <strong>二维码链接</strong>
                          {qrcodeUrl ? (
                            <a
                              className={`${styles.managementLink} ${styles.channelQrLink}`}
                              href={qrcodeUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {qrcodeUrl}
                            </a>
                          ) : (
                            <span className={styles.managementMeta}>暂无二维码链接</span>
                          )}
                          <div className={styles.managementListMeta}>
                            <span>所属用户: {binding.owner_user_id}</span>
                            <span>ClawBot 节点: {baseUrl}</span>
                            <span>更新: {formatDateTime(binding.updated_at)}</span>
                          </div>
                          <div className={styles.managementActionRow}>
                            <button
                              className={styles.managementMinorButton}
                              disabled={pendingBindingId === binding.id}
                              onClick={() => void checkWeixinStatus(binding.id)}
                            >
                              {pendingBindingId === binding.id ? '检查中...' : '检查状态'}
                            </button>
                            <button
                              className={styles.managementMinorButton}
                              disabled={pendingBindingId === binding.id}
                              onClick={() => void refreshWeixinQrcode(binding.id)}
                            >
                              刷新二维码
                            </button>
                            <button
                              className={styles.managementDangerMinorButton}
                              disabled={pendingBindingId === binding.id}
                              onClick={() => void deleteBinding(binding)}
                            >
                              删除绑定
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </section>

          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>飞书绑定</h3>
              <span className={styles.managementMeta}>{feishuBindings.length} 条</span>
            </div>
            <div className={styles.managementToolbar}>
              <input
                className={styles.managementInput}
                value={feishuOwnerUserId}
                onChange={(event) => setFeishuOwnerUserId(event.target.value)}
                placeholder="所属系统用户 ID"
              />
              <input
                className={styles.managementInput}
                value={feishuDisplayName}
                onChange={(event) => setFeishuDisplayName(event.target.value)}
                placeholder="绑定备注名"
              />
              <input
                className={styles.managementInput}
                value={feishuAppId}
                onChange={(event) => setFeishuAppId(event.target.value)}
                placeholder="App ID"
              />
              <input
                className={styles.managementInput}
                value={feishuAppSecret}
                onChange={(event) => setFeishuAppSecret(event.target.value)}
                placeholder="App Secret"
              />
            </div>
            <div className={styles.managementToolbar}>
              <select
                className={styles.managementInput}
                value={feishuDomain}
                onChange={(event) =>
                  setFeishuDomain(event.target.value as 'feishu' | 'lark')
                }
              >
                <option value="feishu">feishu</option>
                <option value="lark">lark</option>
              </select>
              <select
                className={styles.managementInput}
                value={feishuGroupPolicy}
                onChange={(event) =>
                  setFeishuGroupPolicy(event.target.value as 'mention' | 'open')
                }
              >
                <option value="mention">mention</option>
                <option value="open">open</option>
              </select>
              <button
                className={
                  feishuStreaming
                    ? styles.managementButton
                    : styles.managementMinorButton
                }
                onClick={() => setFeishuStreaming((current) => !current)}
              >
                {feishuStreaming ? '长连接已启用' : '启用长连接'}
              </button>
              <button
                className={styles.managementButton}
                disabled={submittingFeishu}
                onClick={() => void createFeishuBinding()}
              >
                {submittingFeishu ? '创建中...' : '新增飞书绑定'}
              </button>
            </div>
            <div className={styles.managementMetaPanel}>
              <span>每条飞书绑定独立保存自己的 app_id / app_secret。</span>
              <span>群聊策略当前支持 mention 与 open。</span>
            </div>
            <div className={styles.managementList}>
              {feishuBindings.length === 0 ? (
                <div className={styles.managementEmpty}>当前还没有飞书绑定。</div>
              ) : (
                feishuBindings.map((binding) => (
                  <div key={binding.id} className={styles.managementListItemStatic}>
                    <div className={styles.managementListHeader}>
                      <strong>{binding.display_name || `绑定 ${binding.id}`}</strong>
                      <span>{getBindingRuntimeStatus(binding)}</span>
                    </div>
                    <p className={styles.managementDescription}>
                      App ID:{' '}
                      {typeof binding.credentials.app_id === 'string'
                        ? maskText(binding.credentials.app_id)
                        : '未配置'}
                    </p>
                    <div className={styles.managementListMeta}>
                      <span>所属用户: {binding.owner_user_id}</span>
                      <span>
                        群策略:{' '}
                        {typeof binding.config.group_policy === 'string'
                          ? binding.config.group_policy
                          : 'mention'}
                      </span>
                      <span>
                        Bot Open ID:{' '}
                        {typeof binding.runtime_state.bot_open_id === 'string'
                          ? binding.runtime_state.bot_open_id
                          : '未识别'}
                      </span>
                      <span>更新: {formatDateTime(binding.updated_at)}</span>
                    </div>
                    <div className={styles.managementActionRow}>
                      <button
                        className={styles.managementDangerMinorButton}
                        disabled={pendingBindingId === binding.id}
                        onClick={() => void deleteBinding(binding)}
                      >
                        {pendingBindingId === binding.id ? '删除中...' : '删除绑定'}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
