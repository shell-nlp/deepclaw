'use client'

import { useCallback, useEffect, useState } from 'react'

import styles from '../ChatInterface.module.css'
import {
  WEIXIN_CLAWBOT_USER_QRCODE_API_PATH,
  WEIXIN_CLAWBOT_USER_QRCODE_STATUS_API_PATH,
} from './constants'
import type {
  WeixinClawBotQrcodeResponse,
  WeixinClawBotQrcodeStatusResponse,
} from './types'
import { fetchJson, getApiUrl } from './utils'

interface WeixinChannelManagementViewProps {
  userId: string
}

function maskToken(value?: string | null): string {
  if (!value) return '未获取'
  if (value.length <= 10) return `${value.slice(0, 2)}***`
  return `${value.slice(0, 6)}...${value.slice(-4)}`
}

function getResponseQrcodeUrl(
  response?: WeixinClawBotQrcodeResponse | WeixinClawBotQrcodeStatusResponse | null
): string {
  const qrcodeUrl = response?.qrcode_url
  if (typeof qrcodeUrl === 'string' && qrcodeUrl.trim()) return qrcodeUrl

  const qrcode = response?.qrcode
  if (
    typeof qrcode === 'string' &&
    (qrcode.startsWith('http://') || qrcode.startsWith('https://'))
  ) {
    return qrcode
  }

  return ''
}

function getBaseUrl(status?: WeixinClawBotQrcodeStatusResponse | null): string {
  return status?.baseurl || status?.base_url || '未获取'
}

function formatRawStatus(status?: WeixinClawBotQrcodeStatusResponse | null): string {
  if (!status) return '暂无状态'
  const payload = {
    status: status.status ?? null,
    has_bot_token: Boolean(status.bot_token),
    baseurl: status.baseurl ?? status.base_url ?? null,
  }
  return JSON.stringify(payload, null, 2)
}

export function WeixinChannelManagementView({
  userId,
}: WeixinChannelManagementViewProps) {
  const [qrcode, setQrcode] = useState<WeixinClawBotQrcodeResponse | null>(null)
  const [status, setStatus] =
    useState<WeixinClawBotQrcodeStatusResponse | null>(null)
  const [loadingQrcode, setLoadingQrcode] = useState(false)
  const [checkingStatus, setCheckingStatus] = useState(false)
  const [autoPolling, setAutoPolling] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const qrcodeUrl = getResponseQrcodeUrl(qrcode) || getResponseQrcodeUrl(status)
  const botToken = status?.bot_token || null
  const connected = Boolean(botToken)
  const connectionLabel = connected
    ? '已连接'
    : autoPolling
      ? '等待扫码'
      : qrcodeUrl
        ? '二维码已生成'
        : '未连接'

  const checkStatus = useCallback(async () => {
    if (!userId.trim()) {
      setError('请先在用户管理里设置当前用户 ID。')
      return
    }

    setCheckingStatus(true)
    setError('')
    try {
      const nextStatus = await fetchJson<WeixinClawBotQrcodeStatusResponse>(
        getApiUrl(WEIXIN_CLAWBOT_USER_QRCODE_STATUS_API_PATH(userId))
      )
      setStatus(nextStatus)
      const nextQrcodeUrl = getResponseQrcodeUrl(nextStatus)
      if (nextQrcodeUrl) {
        setQrcode((current) =>
          getResponseQrcodeUrl(current) ? current : { qrcode_url: nextQrcodeUrl }
        )
      }

      if (nextStatus.bot_token) {
        setAutoPolling(false)
        setNotice('扫码已确认，后端已为当前用户启动微信 ClawBot 轮询。')
      } else if (nextStatus.status) {
        setNotice(`当前扫码状态：${nextStatus.status}`)
      } else {
        setNotice('还没有获取到扫码确认状态。')
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setCheckingStatus(false)
    }
  }, [userId])

  const generateQrcode = useCallback(async () => {
    if (!userId.trim()) {
      setError('请先在用户管理里设置当前用户 ID。')
      return
    }

    setLoadingQrcode(true)
    setError('')
    setNotice('')
    setStatus(null)
    try {
      const nextQrcode = await fetchJson<WeixinClawBotQrcodeResponse>(
        getApiUrl(WEIXIN_CLAWBOT_USER_QRCODE_API_PATH(userId)),
        { method: 'POST' }
      )
      setQrcode(nextQrcode)
      setAutoPolling(true)
      setNotice('二维码已生成，请用当前用户自己的微信扫码登录。')
    } catch (nextError) {
      setAutoPolling(false)
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setLoadingQrcode(false)
    }
  }, [userId])

  useEffect(() => {
    setQrcode(null)
    setStatus(null)
    setAutoPolling(false)
    setNotice('')
    setError('')
    if (userId.trim()) {
      void checkStatus()
    }
  }, [checkStatus, userId])

  useEffect(() => {
    if (!autoPolling || connected) return

    const timer = window.setInterval(() => {
      void checkStatus()
    }, 2000)

    return () => window.clearInterval(timer)
  }, [autoPolling, checkStatus, connected])

  return (
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>Channel Management</span>
          <h2>微信 ClawBot 渠道管理</h2>
          <p>
            每个项目用户都需要扫码接入自己的微信账号。这里会按当前用户 ID 生成登录二维码链接，
            扫码确认后后端会保存该用户的 ClawBot token，并自动启动消息轮询。
          </p>
        </div>
        <div className={styles.managementHeroActions}>
          <button
            className={styles.managementButton}
            disabled={loadingQrcode || !userId.trim()}
            onClick={() => void generateQrcode()}
          >
            {loadingQrcode ? '生成中...' : '生成/刷新登录二维码'}
          </button>
          <button
            className={styles.managementMinorButton}
            disabled={checkingStatus || !userId.trim()}
            onClick={() => void checkStatus()}
          >
            {checkingStatus ? '检查中...' : '检查扫码状态'}
          </button>
        </div>
      </section>

      <div className={styles.managementNoticeRow}>
        {notice ? <div className={styles.managementNotice}>{notice}</div> : null}
        {error ? <div className={styles.managementError}>{error}</div> : null}
      </div>

      <div className={styles.managementSummaryGrid}>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>当前用户</span>
          <strong className={styles.managementSummaryValue}>{userId || '未设置'}</strong>
          <span className={styles.managementMeta}>微信账号会绑定到这个 user_id</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>连接状态</span>
          <strong className={styles.managementSummaryValue}>{connectionLabel}</strong>
          <span className={styles.managementMeta}>
            {autoPolling ? '正在每 2 秒自动检查一次' : '可手动检查最新状态'}
          </span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>Bot Token</span>
          <strong className={styles.managementSummaryValue}>{maskToken(botToken)}</strong>
          <span className={styles.managementMeta}>只展示脱敏值，完整 token 由后端保存</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>ClawBot 节点</span>
          <strong className={styles.managementSummaryValue}>{getBaseUrl(status)}</strong>
          <span className={styles.managementMeta}>扫码确认后由 ClawBot 返回</span>
        </div>
      </div>

      <div className={styles.managementPageGrid}>
        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>登录二维码链接</h3>
            <span className={styles.managementMeta}>
              {qrcodeUrl ? '已生成' : '等待生成'}
            </span>
          </div>

          {qrcodeUrl ? (
            <div className={styles.managementMetaPanel}>
              <span>请复制或打开下面链接，再用当前用户自己的微信扫码。</span>
              <a
                className={styles.managementLink}
                href={qrcodeUrl}
                target="_blank"
                rel="noreferrer"
              >
                {qrcodeUrl}
              </a>
            </div>
          ) : (
            <div className={styles.managementEmpty}>
              还没有二维码链接。点击“生成/刷新登录二维码”开始登录。
            </div>
          )}

          <div className={styles.managementToolbar}>
            <button
              className={styles.managementButton}
              disabled={loadingQrcode || !userId.trim()}
              onClick={() => void generateQrcode()}
            >
              重新生成二维码
            </button>
            <button
              className={styles.managementMinorButton}
              disabled={checkingStatus || !userId.trim()}
              onClick={() => void checkStatus()}
            >
              手动检查状态
            </button>
          </div>
        </section>

        <section className={styles.managementCard}>
          <div className={styles.managementHeader}>
            <h3>状态诊断</h3>
            <span className={styles.managementMeta}>
              {status?.status || (connected ? 'confirmed' : 'unknown')}
            </span>
          </div>

          <div className={styles.managementMetaPanel}>
            <span>绑定策略: 每个 user_id 对应一个独立微信扫码登录态</span>
            <span>消息归属: 后端用当前 user_id 隔离微信会话和 Agent 会话</span>
            <span>轮询策略: 扫码确认后后端自动启动该用户的 ClawBot poll</span>
          </div>

          <textarea
            className={styles.managementTextarea}
            value={formatRawStatus(status)}
            readOnly
            rows={8}
            spellCheck={false}
          />
        </section>
      </div>
    </div>
  )
}
