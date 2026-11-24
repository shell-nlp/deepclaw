'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { REASONING_LABELS, type ChatModelOptions, type ReasoningChoice } from '../utils/reasoning'
import styles from './ChatModelPicker.module.css'

interface Props {
  models: ChatModelOptions
  modelId: string
  choice: ReasoningChoice
  onModelChange: (id: string) => void
  onChoiceChange: (choice: ReasoningChoice) => void
}

/** 在输入框上方显示模型和推理等级。Args: props 为当前配置与选择回调。 */
export function ChatModelPicker({ models, modelId, choice, onModelChange, onChoiceChange }: Props) {
  const panelId = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(null)
  const open = anchor !== null
  const selectedId = modelId || models.default_id
  const selected = models.items.find(model => model.id === selectedId)
  const levels = selected?.reasoning_efforts ?? []
  const labels = { off: '关闭', on: '开启', ...REASONING_LABELS }

  useEffect(() => {
    if (!open) return
    panel.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus({ preventScroll: true })
    const dismissOutside = (event: PointerEvent) => {
      const target = event.target
      if (target instanceof Node && !panel.current?.contains(target) && !trigger.current?.contains(target)) {
        setAnchor(null)
      }
    }
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setAnchor(null)
      trigger.current?.focus()
    }
    const reposition = () => {
      const bounds = trigger.current?.getBoundingClientRect()
      if (bounds) setAnchor({ top: bounds.top, right: document.documentElement.clientWidth - bounds.right })
    }
    document.addEventListener('pointerdown', dismissOutside)
    document.addEventListener('keydown', dismissOnEscape)
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      document.removeEventListener('pointerdown', dismissOutside)
      document.removeEventListener('keydown', dismissOnEscape)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  return <>
    <button
      className={styles.trigger}
      type="button"
      ref={trigger}
      aria-label="模型与推理设置"
      aria-expanded={open}
      aria-controls={open ? panelId : undefined}
      onClick={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect()
        setAnchor(open ? null : { top: bounds.top, right: document.documentElement.clientWidth - bounds.right })
      }}
    >
      <span className={styles.modelName}>{selected?.name ?? '默认模型'}</span>
      <span className={styles.triggerEffort}>{labels[choice]}</span>
      <span aria-hidden="true" className={styles.chevron} />
    </button>
    {anchor && createPortal(
      <div
        role="group"
        aria-label="模型与推理设置"
        className={styles.panel}
        id={panelId}
        ref={panel}
        style={{ top: anchor.top - 8, right: Math.max(8, anchor.right), maxHeight: Math.max(0, anchor.top - 16) }}
      >
        <div className={styles.section}>
          <h3>模型</h3>
          <div className={styles.models}>
            {models.items.length ? models.items.map(model => (
              <button
                key={model.id}
                type="button"
                role="radio"
                aria-checked={model.id === selectedId}
                className={styles.model}
                onClick={() => {
                  onModelChange(model.id === models.default_id ? '' : model.id)
                }}
              >
                <span className={styles.mark} aria-hidden="true">{model.id === selectedId ? '✓' : ''}</span>
                <span className={styles.modelName}>{model.name}</span>
                {model.id === models.default_id && <small>默认</small>}
              </button>
            )) : <div className={styles.empty}>默认模型</div>}
          </div>
        </div>
        <div className={styles.section}>
          <h3>推理等级</h3>
          <div className={styles.levels} aria-label="推理等级">
            {(['off', 'on', ...levels] as const).map(level => (
              <button key={level} type="button" className={styles.level} aria-pressed={level === choice}
                onClick={() => {
                  onChoiceChange(level)
                  setAnchor(null)
                  trigger.current?.focus()
                }}
              >{labels[level]}</button>
            ))}
          </div>
        </div>
      </div>,
      document.body,
    )}
  </>
}
