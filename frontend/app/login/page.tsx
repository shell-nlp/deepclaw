'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'

import styles from './login.module.css'
import {
  clearRememberedLogin,
  clearStoredAuthToken,
  fetchCurrentActor,
  getRememberedLogin,
  getStoredAuthToken,
  normalizeActorPayload,
  normalizeUserToActor,
  revokeAuthToken,
  storeRememberedLogin,
  storeAuthToken,
  submitAuthRequest,
  type ActorState,
} from '@/components/chat-interface/auth'

function normalizeRedirectTarget(value: string | null): string {
  if (!value) {
    return '/#/chat'
  }

  const normalized = value.trim()
  return normalized.startsWith('/') ? normalized : '/#/chat'
}

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [actor, setActor] = useState<ActorState>(() => normalizeActorPayload(null))
  const [token, setToken] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberPassword, setRememberPassword] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)

  const redirectTarget = useMemo(() => {
    if (typeof window === 'undefined') {
      return '/#/chat'
    }

    return normalizeRedirectTarget(
      new URLSearchParams(window.location.search).get('next')
    )
  }, [])

  useEffect(() => {
    const rememberedLogin = getRememberedLogin()
    if (rememberedLogin) {
      setEmail(rememberedLogin.email)
      setPassword(rememberedLogin.password)
      setRememberPassword(true)
    }

    const storedToken = getStoredAuthToken()
    if (!storedToken) {
      setCheckingSession(false)
      return
    }

    setToken(storedToken)
    void fetchCurrentActor(storedToken)
      .then((nextActor) => {
        setActor(nextActor)
      })
      .catch(() => {
        clearStoredAuthToken()
        setToken('')
        setActor(normalizeActorPayload(null))
        setNotice('登录状态已失效，请重新登录。')
      })
      .finally(() => {
        setCheckingSession(false)
      })
  }, [])

  const returnToApp = () => {
    if (typeof window === 'undefined') return
    window.location.assign(redirectTarget)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const normalizedEmail = email.trim().toLowerCase()
    const normalizedPassword = password.trim()
    if (!normalizedEmail || !normalizedPassword) {
      setNotice('')
      setError('请输入邮箱和密码。')
      return
    }

    setLoading(true)
    setNotice('')
    setError('')
    try {
      const result = await submitAuthRequest(mode, normalizedEmail, normalizedPassword)
      if (rememberPassword) {
        storeRememberedLogin({
          email: normalizedEmail,
          password: normalizedPassword,
        })
      } else {
        clearRememberedLogin()
      }
      storeAuthToken(result.token)
      setToken(result.token)
      setActor(normalizeUserToActor(result.user))
      if (!rememberPassword) {
        setPassword('')
      }
      setNotice(mode === 'login' ? '登录成功，正在返回系统。' : '注册成功，正在返回系统。')
      window.setTimeout(() => {
        window.location.assign(redirectTarget)
      }, 180)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '认证失败。')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    setLoading(true)
    try {
      if (token) {
        await revokeAuthToken(token)
      }
    } catch {
      // ignore logout failure
    } finally {
      clearStoredAuthToken()
      setToken('')
      setActor(normalizeActorPayload(null))
      setPassword('')
      setNotice('已退出登录，你仍可作为游客继续使用。')
      setError('')
      setLoading(false)
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.grid} />
      <div className={styles.glowPrimary} />
      <div className={styles.glowSecondary} />

      <section className={styles.shell}>
        <div className={styles.brandPanel}>
          <span className={styles.brandBadge}>AI</span>
          <div className={styles.brandCopy}>
            <p className={styles.kicker}>DeepClaw Access</p>
            <h1>DeepClaw</h1>
            <p className={styles.description}>
              统一的智能体工作台，支持聊天问答、MCP 工具接入、知识库管理和图检索
              RAG。游客可直接进入系统，登录后可解锁上传与管理能力。
            </p>
          </div>

          <div className={styles.featureList}>
            <article className={styles.featureCard}>
              <strong>游客模式</strong>
              <span>无需注册即可进入，适合先体验聊天和浏览能力。</span>
            </article>
            <article className={styles.featureCard}>
              <strong>用户账号</strong>
              <span>登录后可上传知识库、上传技能，并隔离个人聊天数据。</span>
            </article>
            <article className={styles.featureCard}>
              <strong>管理员账号</strong>
              <span>除普通能力外，还可创建用户、调整角色和管理账号状态。</span>
            </article>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <div>
              <p className={styles.cardEyebrow}>账号入口</p>
              <h2>{actor.isGuest ? '登录或注册' : '当前账号'}</h2>
            </div>
            <button
              type="button"
              className={styles.ghostButton}
              onClick={returnToApp}
            >
              继续以游客身份使用
            </button>
          </div>

          {checkingSession ? (
            <div className={styles.sessionPlaceholder}>正在检查当前登录状态...</div>
          ) : null}

          {!checkingSession && notice ? (
            <div className={styles.notice}>{notice}</div>
          ) : null}

          {!checkingSession && error ? <div className={styles.error}>{error}</div> : null}

          {!checkingSession && actor.isGuest ? (
            <>
              <div className={styles.modeTabs}>
                <button
                  type="button"
                  className={`${styles.modeTab} ${
                    mode === 'login' ? styles.modeTabActive : ''
                  }`}
                  onClick={() => setMode('login')}
                >
                  登录
                </button>
                <button
                  type="button"
                  className={`${styles.modeTab} ${
                    mode === 'register' ? styles.modeTabActive : ''
                  }`}
                  onClick={() => setMode('register')}
                >
                  注册
                </button>
              </div>

              <form className={styles.form} onSubmit={handleSubmit}>
                <label className={styles.field}>
                  <span>邮箱</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="name@example.com"
                    autoComplete="email"
                  />
                </label>

                <label className={styles.field}>
                  <span>密码</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="至少 8 位密码"
                    autoComplete={
                      mode === 'login' ? 'current-password' : 'new-password'
                    }
                  />
                </label>

                <label className={styles.rememberRow}>
                  <input
                    type="checkbox"
                    checked={rememberPassword}
                    onChange={(event) => setRememberPassword(event.target.checked)}
                  />
                  <span>记住密码</span>
                </label>

                <button type="submit" className={styles.primaryButton} disabled={loading}>
                  {loading ? '提交中...' : mode === 'login' ? '登录' : '注册并登录'}
                </button>
              </form>

              <p className={styles.helperText}>
                注册后会自动登录。当前先不做邮箱验证码，邮箱需保持唯一。
              </p>
            </>
          ) : null}

          {!checkingSession && !actor.isGuest ? (
            <div className={styles.accountCard}>
              <div className={styles.accountMeta}>
                <span className={styles.accountRole}>
                  {actor.role === 'admin' ? '管理员账号' : '普通用户'}
                </span>
                <strong>{actor.email || actor.userId}</strong>
                <span>用户 ID: {actor.userId}</span>
              </div>

              <p className={styles.helperText}>
                当前会话已经登录。你可以返回系统继续使用，也可以先退出再切换其他账号。
              </p>

              <div className={styles.actionRow}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={returnToApp}
                >
                  返回系统
                </button>
                <button
                  type="button"
                  className={styles.dangerButton}
                  disabled={loading}
                  onClick={() => void handleLogout()}
                >
                  {loading ? '处理中...' : '退出登录'}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </main>
  )
}
