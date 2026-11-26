'use client'

import { useEffect, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import type { RequestJson } from '../management/schedules'
import type { ChatFile } from '../utils/chatFiles'

interface FavoriteFileOptionsProps {
  requestJson: RequestJson
  draftFiles: ChatFile[]
  disabled: boolean
  onChange: (files: ChatFile[]) => void
  onNavigate: () => void
}

type FavoritePage = { files: ChatFile[]; next_offset: number | null }

/**
 * 分页显示收藏文件，并按 ID 加入当前消息的附件草稿。
 *
 * Args:
 *   props: 收藏接口请求、当前草稿、禁用状态与管理页导航。
 */
export function FavoriteFileOptions({ requestJson, draftFiles, disabled, onChange, onNavigate }: FavoriteFileOptionsProps) {
  const [items, setItems] = useState<ChatFile[]>([])
  const [offset, setOffset] = useState(0)
  const [nextOffset, setNextOffset] = useState<number | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const selected = new Set(draftFiles.map((file) => file.file_id))
  const atLimit = draftFiles.length >= 4

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setFailed(false)
    void requestJson<FavoritePage>(`/api/files?favorite=true&offset=${offset}`, { signal: controller.signal })
      .then((page) => {
        if (controller.signal.aborted) return
        const favorites = page.files.filter((file) => file.favorite)
        setItems((current) => offset === 0
          ? favorites
          : [...new Map([...current, ...favorites].map((file) => [file.file_id, file])).values()])
        setNextOffset(page.next_offset)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [attempt, offset, requestJson])

  return (
    <div className={styles.knowledgePickerFiles}>
      {items.map((file) => {
        const checked = selected.has(file.file_id)
        return (
          <label key={file.file_id} className={styles.knowledgePickerItem}>
            <input type="checkbox" checked={checked} disabled={disabled || (!checked && atLimit)}
              onChange={() => onChange(checked
                ? draftFiles.filter((item) => item.file_id !== file.file_id)
                : [...draftFiles, file])} />
            <span className={styles.knowledgePickerItemText}>
              <strong title={file.name}>{file.name}</strong>
              <small>{file.extension.slice(1).toUpperCase()}</small>
            </span>
          </label>
        )
      })}
      {loading ? (
        <div className={styles.knowledgePickerEmpty} role="status">正在加载收藏文件…</div>
      ) : failed ? (
        <div className={styles.knowledgePickerEmpty} role="status">
          <span>收藏文件加载失败。</span>
          <button type="button" className={styles.knowledgePickerLink} onClick={() => setAttempt(attempt + 1)}>重试</button>
        </div>
      ) : items.length === 0 ? (
        <div className={styles.knowledgePickerEmpty}>
          <span>还没有收藏文件。</span>
          <button type="button" className={styles.knowledgePickerLink} onClick={onNavigate}>去收藏文件</button>
        </div>
      ) : nextOffset !== null ? (
        <button type="button" className={styles.knowledgePickerMore} onClick={() => {
          setLoading(true)
          setOffset(nextOffset)
        }}>加载更多</button>
      ) : null}
    </div>
  )
}
