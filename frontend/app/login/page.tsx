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
} from '@/components/chat/utils/auth'

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
  const [username, setUsername] = useState('')
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
      setUsername(rememberedLogin.username)
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

    const normalizedUsername = username.trim().toLowerCase()
    const normalizedPassword = password.trim()
    if (!normalizedUsername || !normalizedPassword) {
      setNotice('')
      setError('请输入用户名和密码。')
      return
    }

    setLoading(true)
    setNotice('')
    setError('')
    try {
      const result = await submitAuthRequest(
        mode,
        normalizedUsername,
        normalizedPassword,
        email
      )
      if (rememberPassword) {
        storeRememberedLogin({
          username: normalizedUsername,
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
      <aside className={styles.brandPanel}>
        <span className={styles.brandBadge} aria-hidden="true">D</span>

        <div className={styles.brandCopy}>
          <p className={styles.kicker}>DeepClaw Access</p>
          <h1>DeepClaw</h1>
          <p className={styles.description}>
            统一的智能体工作台：聊天问答、MCP 工具、知识库与 RAG 检索都在同一个界面里。
          </p>
        </div>

        <div className={styles.featureList}>
          <article className={styles.featureCard}>
            <strong>游客模式</strong>
            <span>无需注册即可聊天和浏览。</span>
          </article>
          <article className={styles.featureCard}>
            <strong>用户账号</strong>
            <span>登录后隔离个人数据，可上传知识库与技能。</span>
          </article>
          <article className={styles.featureCard}>
            <strong>管理员账号</strong>
            <span>额外拥有用户管理、角色与权限策略配置能力。</span>
          </article>
        </div>

        <div className={styles.brandFooter}>
          <button
            type="button"
            className={styles.ghostButton}
            onClick={returnToApp}
          >
            返回系统
          </button>
        </div>
      </aside>

      <section className={styles.content}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <p className={styles.cardEyebrow}>
              {actor.isGuest ? '账号入口' : '当前账号'}
            </p>
            <h2>{actor.isGuest ? '登录或注册' : '已登录'}</h2>
          </div>

          {checkingSession ? (
            <div className={styles.sessionPlaceholder}>正在检查当前登录状态...</div>
          ) : null}

          {!checkingSession && notice ? (
            <div className={styles.notice} role="status">{notice}</div>
          ) : null}

          {!checkingSession && error ? (
            <div className={styles.error} role="alert">{error}</div>
          ) : null}

          {!checkingSession && actor.isGuest ? (
            <>
              <div className={styles.modeTabs} role="tablist" aria-label="账号操作">
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'login'}
                  className={`${styles.modeTab} ${mode === 'login' ? styles.modeTabActive : ''}`}
                  onClick={() => setMode('login')}
                >
                  登录
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mode === 'register'}
                  className={`${styles.modeTab} ${mode === 'register' ? styles.modeTabActive : ''}`}
                  onClick={() => setMode('register')}
                >
                  注册
                </button>
              </div>

              <form className={styles.form} onSubmit={handleSubmit}>
                <label className={styles.field}>
                  <span>用户名</span>
                  <input
                    type="text"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="例如 deepclaw"
                    autoComplete="username"
                    autoFocus
                  />
                </label>

                <label className={styles.field}>
                  <span>密码</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="至少 8 位"
                    autoComplete={
                      mode === 'login' ? 'current-password' : 'new-password'
                    }
                  />
                </label>

                {mode === 'register' ? (
                  <label className={styles.field}>
                    <span>邮箱（可选）</span>
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="仅用于资料展示，不参与登录"
                      autoComplete="email"
                    />
                  </label>
                ) : null}

                <label className={styles.rememberRow}>
                  <input
                    type="checkbox"
                    checked={rememberPassword}
                    onChange={(event) => setRememberPassword(event.target.checked)}
                  />
                  <span>记住用户名和密码</span>
                </label>

                <button type="submit" className={styles.primaryButton} disabled={loading}>
                  {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}
                </button>
              </form>

              <p className={styles.helperText}>
                使用用户名登录，用户名需唯一；邮箱为可选资料，不参与登录。
              </p>
            </>
          ) : null}

          {!checkingSession && !actor.isGuest ? (
            <div className={styles.accountCard}>
              <div className={styles.accountMeta}>
                <span className={styles.accountRole}>
                  {actor.role === 'admin' ? '管理员' : '普通用户'}
                </span>
                <strong>{actor.username || actor.email || actor.userId}</strong>
                <span>用户 ID：{actor.userId}</span>
              </div>

              <p className={styles.helperText}>
                当前会话已登录。可以返回系统继续使用，也可以退出后切换账号。
              </p>

              <div className={styles.actionRow}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={returnToApp}
                >
                  进入系统
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
