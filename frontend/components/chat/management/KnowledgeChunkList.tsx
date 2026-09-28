'use client'

import { useState } from 'react'

import styles from '../../ChatInterface.module.css'
import { Pagination } from '../shared/Pagination'
import type { KnowledgeChunk } from '../../chat-interface/types'

interface KnowledgeChunkListProps {
  chunks: KnowledgeChunk[]
  total: number
  page: number
  pageTotal: number
  loading: boolean
  writeDisabled: boolean
  onPageChange: (page: number | ((prev: number) => number)) => void
  onUpdateChunk: (
    chunk: KnowledgeChunk,
    changes: { content?: string; state?: boolean }
  ) => void | Promise<void>
}

function chunkIsEnabled(chunk: KnowledgeChunk) {
  return chunk.metadata.state !== false
}

function chunkIndexLabel(chunk: KnowledgeChunk) {
  const segment = chunk.segment_id
  if (segment === null || segment === undefined || segment === '') return '—'
  const text = String(segment)
  return /^\d+$/.test(text) ? text.padStart(3, '0') : text
}

export function KnowledgeChunkList({
  chunks,
  total,
  page,
  pageTotal,
  loading,
  writeDisabled,
  onPageChange,
  onUpdateChunk,
}: KnowledgeChunkListProps) {
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null)
  const [editingChunk, setEditingChunk] = useState<KnowledgeChunk | null>(null)
  const [draftContent, setDraftContent] = useState('')
  const [savingChunk, setSavingChunk] = useState(false)

  const openEditor = (chunk: KnowledgeChunk) => {
    setEditingChunk(chunk)
    setDraftContent(chunk.content)
  }

  const closeEditor = () => {
    setEditingChunk(null)
    setDraftContent('')
  }

  const submitEditor = async () => {
    if (!editingChunk) return
    setSavingChunk(true)
    try {
      await onUpdateChunk(editingChunk, { content: draftContent })
      closeEditor()
    } finally {
      setSavingChunk(false)
    }
  }

  return (
    <>
      <div className={styles.managementHeader}>
        <div className={styles.managementKnowledgeSectionTitle}>
          <h3>切片</h3>
          <p>关闭的切片不再参与检索。</p>
        </div>
        <span className={styles.managementMeta}>
          {loading ? '加载中...' : `共 ${total} 条`}
        </span>
      </div>

      <ul className={styles.chunkList}>
        {chunks.length === 0 ? (
          <li className={styles.chunkEmpty}>这篇文档还没有切片。</li>
        ) : (
          chunks.map((chunk) => {
            const enabled = chunkIsEnabled(chunk)
            const expanded = expandedChunkId === chunk.chunk_id
            const title = String(chunk.metadata.title ?? '').trim()
            const pageNumber = chunk.metadata.pages_number
            return (
              <li
                key={chunk.chunk_id}
                className={styles.chunkRow}
                data-state={enabled ? 'on' : 'off'}
              >
                <span className={styles.chunkIndex}>{chunkIndexLabel(chunk)}</span>
                <button
                  type="button"
                  className={styles.chunkBody}
                  aria-expanded={expanded}
                  onClick={() =>
                    setExpandedChunkId(expanded ? null : chunk.chunk_id)
                  }
                >
                  <span className={styles.chunkTitle}>
                    {title || '未命名片段'}
                  </span>
                  <span className={expanded ? styles.chunkTextOpen : styles.chunkText}>
                    {chunk.content}
                  </span>
                  <span className={styles.chunkMeta}>
                    <span>第 {pageNumber === null || pageNumber === undefined ? '-' : String(pageNumber)} 页</span>
                    <span>{chunk.content.length} 字</span>
                    {enabled ? null : (
                      <span className={styles.chunkDisabledTag}>已停用</span>
                    )}
                    <span>{expanded ? '收起' : '展开全文'}</span>
                  </span>
                </button>
                <div className={styles.chunkActions}>
                  <label className={styles.chunkSwitch}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={writeDisabled}
                      aria-label={enabled ? '停用该切片' : '启用该切片'}
                      onChange={() =>
                        void onUpdateChunk(chunk, { state: !enabled })
                      }
                    />
                    <span className={styles.chunkSwitchTrack} aria-hidden="true" />
                  </label>
                  <button
                    type="button"
                    className={styles.chunkEditButton}
                    disabled={writeDisabled}
                    onClick={() => openEditor(chunk)}
                  >
                    编辑
                  </button>
                </div>
              </li>
            )
          })
        )}
      </ul>

      <Pagination
        page={page}
        pageTotal={pageTotal}
        total={total}
        onPrev={() => onPageChange((prev) => Math.max(1, prev - 1))}
        onNext={() => onPageChange((prev) => Math.min(pageTotal, prev + 1))}
      />

      {editingChunk ? (
        <div className={styles.extensionDialogOverlay} role="presentation">
          <div
            className={`${styles.extensionDialog} ${styles.chunkEditorDialog}`}
            role="dialog"
            aria-modal="true"
            aria-label="编辑切片"
          >
            <header className={styles.extensionDialogHeader}>
              <div>
                <h3>编辑切片 {chunkIndexLabel(editingChunk)}</h3>
                <p className={styles.extensionDialogHint}>
                  正文保存后会重新生成向量，并立即用于检索。
                </p>
              </div>
              <button
                type="button"
                className={styles.extensionIconButton}
                aria-label="关闭"
                onClick={closeEditor}
              >
                ×
              </button>
            </header>
            <textarea
              className={styles.chunkEditorInput}
              value={draftContent}
              rows={12}
              onChange={(event) => setDraftContent(event.target.value)}
            />
            <footer className={styles.extensionDialogActions}>
              <button
                type="button"
                className={styles.extensionSecondaryButton}
                onClick={closeEditor}
              >
                取消
              </button>
              <button
                type="button"
                className={styles.extensionPrimaryButton}
                disabled={savingChunk || !draftContent.trim()}
                onClick={() => void submitEditor()}
              >
                {savingChunk ? '保存中...' : '保存'}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </>
  )
}
