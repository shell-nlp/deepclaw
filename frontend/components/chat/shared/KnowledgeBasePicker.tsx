'use client'

import { useEffect, useRef, type ReactNode } from 'react'

import styles from '../../ChatInterface.module.css'
import type { KnowledgeBase } from '../../chat-interface/types'

interface KnowledgeBasePickerProps {
  open: boolean
  options: KnowledgeBase[]
  selectedIds: string[]
  loading: boolean
  disabled: boolean
  onOpenChange: (open: boolean) => void
  onSelectionChange: (ids: string[]) => void
  onNavigateToKnowledge: () => void
}

function KnowledgeIcon() {
  return (
    <svg
      aria-hidden="true"
      className={styles.toggleIcon}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      <path d="M5.5 5.8h5.1c1.1 0 2 .9 2 2v10.7c0-1.1-.9-2-2-2H5.5z" />
      <path d="M18.5 5.8h-5.1c-1.1 0-2 .9-2 2v10.7c0-1.1.9-2 2-2h5.1z" />
    </svg>
  )
}

function ChevronIcon({ open }: { open: boolean }): ReactNode {
  return (
    <svg
      aria-hidden="true"
      className={open ? styles.knowledgePickerChevronOpen : styles.knowledgePickerChevron}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

/**
 * 渲染输入框底部的知识库选择器：默认全选，可逐项勾选。
 *
 * Args:
 *   open: 选择面板是否展开。
 *   options: 可选知识库列表。
 *   selectedIds: 已选中的知识库 ID。
 *   loading: 是否正在加载知识库列表。
 *   disabled: 是否禁用交互。
 *   onOpenChange: 展开状态变更回调。
 *   onSelectionChange: 选中集合变更回调。
 *   onNavigateToKnowledge: 跳转知识库管理页回调。
 */
export function KnowledgeBasePicker({
  open,
  options,
  selectedIds,
  loading,
  disabled,
  onOpenChange,
  onSelectionChange,
  onNavigateToKnowledge,
}: KnowledgeBasePickerProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const selectAllRef = useRef<HTMLInputElement | null>(null)
  const selectedSet = new Set(selectedIds)
  const allSelected = options.length > 0 && selectedIds.length === options.length
  const partiallySelected = selectedIds.length > 0 && !allSelected

  useEffect(() => {
    if (!open) return
    if (selectAllRef.current) selectAllRef.current.indeterminate = partiallySelected
  }, [open, partiallySelected])

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onOpenChange(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onOpenChange(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onOpenChange, open])

  const toggleOption = (knowledgeBaseId: string) => {
    onSelectionChange(
      selectedSet.has(knowledgeBaseId)
        ? selectedIds.filter((item) => item !== knowledgeBaseId)
        : [...selectedIds, knowledgeBaseId]
    )
  }

  const active = selectedIds.length > 0
  const valueLabel = allSelected
    ? '全部知识库'
    : selectedIds.length === 1
      ? (options.find((item) => item.knowledge_base_id === selectedIds[0])?.name ??
        '已选 1 个')
      : `已选 ${selectedIds.length} 个`

  return (
    <div className={styles.knowledgePicker} ref={rootRef}>
      <button
        type="button"
        className={active ? styles.toggleActive : styles.toggle}
        title={active ? valueLabel : '选择知识库'}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => onOpenChange(!open)}
      >
        <KnowledgeIcon />
        <span className={styles.toggleLabel}>知识库</span>
        {active ? (
          <span className={styles.knowledgePickerValue}>
            {allSelected ? '全部' : valueLabel}
          </span>
        ) : null}
        <ChevronIcon open={open} />
      </button>

      {open ? (
        <div className={styles.knowledgePickerPanel} role="dialog" aria-label="选择知识库">
          <header className={styles.knowledgePickerHeader}>
            <strong>选择知识库</strong>
            <span>选中的知识库会一起参与检索。</span>
          </header>

          {loading ? (
            <div className={styles.knowledgePickerEmpty}>正在加载知识库...</div>
          ) : options.length === 0 ? (
            <div className={styles.knowledgePickerEmpty}>
              <span>还没有可用的知识库。</span>
              <button
                type="button"
                className={styles.knowledgePickerLink}
                onClick={() => {
                  onOpenChange(false)
                  onNavigateToKnowledge()
                }}
              >
                去创建知识库
              </button>
            </div>
          ) : (
            <>
              <label className={styles.knowledgePickerAll}>
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) =>
                    onSelectionChange(
                      event.target.checked
                        ? options.map((option) => option.knowledge_base_id)
                        : []
                    )
                  }
                />
                <span>全部知识库</span>
                <span className={styles.knowledgePickerAllCount}>{options.length} 个</span>
              </label>
              <ul className={styles.knowledgePickerList}>
                {options.map((option) => (
                  <li key={option.knowledge_base_id}>
                    <label className={styles.knowledgePickerItem}>
                      <input
                        type="checkbox"
                        checked={selectedSet.has(option.knowledge_base_id)}
                        onChange={() => toggleOption(option.knowledge_base_id)}
                      />
                      <span className={styles.knowledgePickerItemText}>
                        <strong>{option.name}</strong>
                        <small>
                          {option.document_count} 文档 · {option.chunk_count} 切片
                        </small>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}

          <footer className={styles.knowledgePickerFooter}>
            <span>
              已选 {selectedIds.length} / {options.length}
            </span>
            <button
              type="button"
              className={styles.knowledgePickerDone}
              onClick={() => onOpenChange(false)}
            >
              完成
            </button>
          </footer>
        </div>
      ) : null}
    </div>
  )
}
