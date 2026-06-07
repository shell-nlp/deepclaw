'use client'

import { useEffect, useRef } from 'react'

import { useRouter } from 'next/navigation'

import styles from '../ChatInterface.module.css'
import type { ActorState } from './auth'

interface AccountPanelProps {
  actor: ActorState
  open: boolean
  onOpenChange: (open: boolean) => void
  onLogout: () => void | Promise<void>
}

function getAccountLabel(actor: ActorState): string {
  if (actor.isGuest) return '游客'
  if (actor.email) return actor.email
  return actor.userId
}

function getAccountSubLabel(actor: ActorState): string {
  if (actor.isGuest) return '可直接体验，写入功能需登录'
  return actor.role === 'admin' ? '管理员账号' : '普通用户'
}

function getLoginHref(): string {
  if (typeof window === 'undefined') {
    return '/login'
  }

  const next = `${window.location.pathname}${window.location.hash || '#/chat'}`
  return `/login?next=${encodeURIComponent(next)}`
}

export function AccountPanel({
  actor,
  open,
  onOpenChange,
  onLogout,
}: AccountPanelProps) {
  const router = useRouter()
  const shellRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open || actor.isGuest) return

    const handlePointerDown = (event: PointerEvent) => {
      if (!shellRef.current?.contains(event.target as Node)) {
        onOpenChange(false)
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onOpenChange(false)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    window.addEventListener('keydown', handleEscape)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown)
      window.removeEventListener('keydown', handleEscape)
    }
  }, [actor.isGuest, onOpenChange, open])

  const handleEntryClick = () => {
    if (actor.isGuest) {
      router.push(getLoginHref())
      return
    }

    onOpenChange(!open)
  }

  return (
    <div className={styles.accountPanelShell} ref={shellRef}>
      <button type="button" className={styles.accountEntry} onClick={handleEntryClick}>
        <span className={styles.accountAvatar}>
          {actor.isGuest ? '游' : (actor.email || actor.userId).slice(0, 1).toUpperCase()}
        </span>
        <span className={styles.accountMeta}>
          <strong>{getAccountLabel(actor)}</strong>
          <span>{getAccountSubLabel(actor)}</span>
        </span>
      </button>

      {open && !actor.isGuest ? (
        <div className={styles.accountMenu}>
          <div className={styles.managementHeader}>
            <div>
              <h3>账号中心</h3>
              <p className={styles.accountHint}>当前会话已绑定此账号，知识库和聊天数据会按账号隔离。</p>
            </div>
            <span className={styles.accountRoleBadge}>
              {actor.role === 'admin' ? '管理员' : '普通用户'}
            </span>
          </div>

          <div className={styles.managementMetaPanel}>
            <span>邮箱: {actor.email || '-'}</span>
            <span>用户 ID: {actor.userId}</span>
          </div>

          <div className={styles.accountMenuActions}>
            <button
              type="button"
              className={styles.managementMinorButton}
              onClick={() => onOpenChange(false)}
            >
              关闭
            </button>
            <button
              type="button"
              className={styles.managementDangerMinorButton}
              onClick={() => void onLogout()}
            >
              退出登录
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
