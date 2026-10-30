'use client'

import { useEffect, useRef, useState } from 'react'
import sharedStyles from '../../ChatInterface.module.css'
import panelStyles from './InterruptPanel.module.css'
import { InterruptArgFields } from './InterruptArgFields'
import {
  cloneInterruptArgs, getAskUserArgs, getInterruptActionArgs,
  isDecisionAllowedForAllActions, isInterruptDecisionAllowed, updateValueAtPath,
  type InterruptArgPath, type InterruptEditedAction,
} from './utils'
import type { InterruptData } from '../utils/types'

const styles = { ...sharedStyles, ...panelStyles }

interface InterruptPanelProps {
  showInterrupt: boolean
  interruptData: InterruptData | null
  onInterruptAction: (decision: 'approve' | 'reject' | 'edit', editedActions?: InterruptEditedAction[]) => void | Promise<void>
  onAskUserResponse: (answer: string) => void | Promise<void>
}

/**
 * 展示人工审批和提问，管理参数编辑及回答草稿。
 *
 * Args:
 *   showInterrupt: 是否展示待处理的人工确认。
 *   interruptData: 当前中断的请求和允许操作。
 *   onInterruptAction: 提交审批决定的回调。
 *   onAskUserResponse: 提交问题回答的回调。
 */
export function InterruptPanel({ showInterrupt, interruptData, onInterruptAction, onAskUserResponse }: InterruptPanelProps) {
  const [isEditingInterruptArgs, setIsEditingInterruptArgs] = useState(false)
  const [interruptArgsDrafts, setInterruptArgsDrafts] = useState<
    Record<string, unknown>[]
  >([])
  const interruptEditorRefs = useRef<
    Array<HTMLInputElement | HTMLTextAreaElement | null>
  >([])
  const [askUserSelection, setAskUserSelection] = useState<string[]>([])
  const [askUserCustomAnswer, setAskUserCustomAnswer] = useState('')
  const askUserArgs = interruptData ? getAskUserArgs(interruptData) : null
  const canEditInterrupt =
    interruptData && isDecisionAllowedForAllActions(interruptData, 'edit')

  useEffect(() => {
    setIsEditingInterruptArgs(false)
    setInterruptArgsDrafts(
      interruptData?.action_requests.map((action) =>
        cloneInterruptArgs(getInterruptActionArgs(action))
      ) || []
    )
    interruptEditorRefs.current = []
    setAskUserSelection([])
    setAskUserCustomAnswer('')
  }, [interruptData])

  /**
   * 更新指定工具的参数草稿。
   *
   * Args:
   *   actionIndex: 工具请求下标。
   *   path: 字段路径。
   *   value: 新参数值。
   */
  const updateInterruptArgDraft = (
    actionIndex: number,
    path: InterruptArgPath,
    value: unknown
  ) => {
    setInterruptArgsDrafts((prev) =>
      prev.map((draft, index) =>
        index === actionIndex
          ? (updateValueAtPath(draft, path, value) as Record<string, unknown>)
          : draft
      )
    )
  }

  /**
   * 进入参数编辑或提交修改后的审批。
   *
   * Args:
   *   无。
   */
  const handleEditInterrupt = () => {
    if (!interruptData || !canEditInterrupt) return

    if (!isEditingInterruptArgs) {
      setIsEditingInterruptArgs(true)
      window.setTimeout(() => {
        interruptEditorRefs.current[0]?.focus()
      }, 0)
      return
    }

    void onInterruptAction(
      'edit',
      interruptData.action_requests.map((action, index) => ({
        name: action.name,
        args: interruptArgsDrafts[index] || getInterruptActionArgs(action),
      }))
    )
  }

  return showInterrupt && interruptData && askUserArgs ? (
      <div className={styles.askUserPanel}>
        <div className={styles.askUserCard}>
          <div className={styles.askUserHeader}>
            <span>{askUserArgs.header || '需要你的回答'}</span>
            <span className={styles.askUserCount}>1/1 个问题</span>
          </div>
          <p className={styles.askUserQuestion}>{askUserArgs.question}</p>
          {(askUserArgs.options?.length || askUserArgs.custom !== false) && (
            <span className={styles.askUserHint}>
              {askUserArgs.multiple ? '可选择一个或多个答案' : '选择一个答案'}
            </span>
          )}
          <div className={styles.askUserChoices}>
            {askUserArgs.options?.map((option) => {
              const selected = askUserSelection.includes(option.label)
              return (
                <label
                  className={`${styles.askUserChoice} ${
                    selected ? styles.askUserChoiceSelected : ''
                  }`}
                  key={option.label}
                >
                  <input
                    checked={selected}
                    className={styles.askUserChoiceInput}
                    name="ask-user-answer"
                    onChange={() => {
                      setAskUserSelection((current) =>
                        askUserArgs.multiple
                          ? selected
                            ? current.filter((item) => item !== option.label)
                            : [...current, option.label]
                          : [option.label]
                      )
                    }}
                    type={askUserArgs.multiple ? 'checkbox' : 'radio'}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    {option.description && <small>{option.description}</small>}
                  </span>
                </label>
              )
            })}
            {askUserArgs.custom !== false && (
              <label
                className={`${styles.askUserChoice} ${
                  askUserSelection.includes('__custom__')
                    ? styles.askUserChoiceSelected
                    : ''
                }`}
              >
                <input
                  checked={askUserSelection.includes('__custom__')}
                  className={styles.askUserChoiceInput}
                  name="ask-user-answer"
                  onChange={() =>
                    setAskUserSelection((current) =>
                      askUserArgs.multiple
                        ? current.includes('__custom__')
                          ? current.filter((item) => item !== '__custom__')
                          : [...current, '__custom__']
                        : ['__custom__']
                    )
                  }
                  type={askUserArgs.multiple ? 'checkbox' : 'radio'}
                />
                <span className={styles.askUserCustomContent}>
                  <strong>输入自己的答案</strong>
                  <input
                    aria-label="输入自己的答案"
                    className={styles.askUserCustomInput}
                    onChange={(event) => setAskUserCustomAnswer(event.currentTarget.value)}
                    onClick={(event) => event.stopPropagation()}
                    onFocus={() =>
                      setAskUserSelection((current) =>
                        askUserArgs.multiple
                          ? current.includes('__custom__')
                            ? current
                            : [...current, '__custom__']
                          : ['__custom__']
                      )
                    }
                    placeholder="输入你的答案..."
                    value={askUserCustomAnswer}
                  />
                </span>
              </label>
            )}
          </div>
        </div>
        <div className={styles.askUserButtons}>
          <button
            className={styles.askUserIgnoreButton}
            onClick={() => void onAskUserResponse('用户选择忽略此问题。')}
            type="button"
          >
            忽略
          </button>
          <button
            className={styles.askUserSubmitButton}
            disabled={
              askUserSelection.length === 0 ||
              (askUserSelection.includes('__custom__') && !askUserCustomAnswer.trim())
            }
            onClick={() => {
              const answers = askUserSelection.map((item) =>
                item === '__custom__' ? askUserCustomAnswer.trim() : item
              )
              void onAskUserResponse(
                askUserArgs.multiple ? answers.join('、') : answers[0]
              )
            }}
            type="button"
          >
            提交
          </button>
        </div>
      </div>
    ) : showInterrupt && interruptData ? (
      <section className={styles.interruptPanel} aria-label="工具执行确认">
        <header className={styles.interruptHeader}>
          <span className={styles.approvalIcon} aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3 4.5 6v5c0 4.6 3.1 8 7.5 10 4.4-2 7.5-5.4 7.5-10V6L12 3Z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </span>
          <div className={styles.headerCopy}>
            <h3>确认后继续</h3>
            <p>请检查以下操作，确认后智能体将继续执行。</p>
          </div>
          <span className={styles.pendingBadge}>等待确认</span>
        </header>
        <div className={styles.interruptContent}>
          {interruptData.action_requests.map((action, index) => (
            <section key={`${action.name}_${index}`} className={styles.interruptAction} aria-label={action.name}>
              <div className={styles.interruptActionHeader}>
                <span className={styles.toolGlyph} aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m8 5-6 7 6 7m8-14 6 7-6 7m-3-15-2 18" />
                  </svg>
                </span>
                <span className={styles.interruptToolName}>{action.name}</span>
                {interruptData.action_requests.length > 1 && <span className={styles.actionCount}>操作 {index + 1} / {interruptData.action_requests.length}</span>}
              </div>
              {action.description && action.description !== '工具执行等待批准' && (
                <p className={styles.interruptDescription}>{action.description}</p>
              )}
              <div className={styles.interruptArgsSection}>
                <div className={styles.parameterHeading}>
                  <span>执行参数</span>
                  {isEditingInterruptArgs && <span className={styles.editingBadge}>正在编辑</span>}
                </div>
                <InterruptArgFields
                  value={interruptArgsDrafts[index] || getInterruptActionArgs(action)}
                  path={[]}
                  disabled={!isEditingInterruptArgs || !isInterruptDecisionAllowed(interruptData, index, 'edit')}
                  inputRef={(element) => { interruptEditorRefs.current[index] = element }}
                  onChange={(path, value) => updateInterruptArgDraft(index, path, value)}
                />
              </div>
            </section>
          ))}
        </div>
        <footer className={styles.interruptButtons}>
          <button type="button" className={`${styles.interruptBtn} ${styles.reject}`}
            onClick={() => void onInterruptAction('reject')}
            disabled={!isDecisionAllowedForAllActions(interruptData, 'reject')}>拒绝执行</button>
          <div className={styles.primaryActions}>
            {isEditingInterruptArgs ? (
              <button type="button" className={`${styles.interruptBtn} ${styles.edit}`} onClick={() => {
                setIsEditingInterruptArgs(false)
                setInterruptArgsDrafts(interruptData.action_requests.map((action) => cloneInterruptArgs(getInterruptActionArgs(action))))
              }}>取消编辑</button>
            ) : (
              <button type="button" className={`${styles.interruptBtn} ${styles.edit}`}
                onClick={handleEditInterrupt} disabled={!canEditInterrupt}>编辑参数</button>
            )}
            <button type="button" className={`${styles.interruptBtn} ${styles.approve}`}
              onClick={isEditingInterruptArgs ? handleEditInterrupt : () => void onInterruptAction('approve')}
              disabled={isEditingInterruptArgs ? !canEditInterrupt : !isDecisionAllowedForAllActions(interruptData, 'approve')}>
              <svg aria-hidden="true" width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m4 10 4 4 8-8" /></svg>
              {isEditingInterruptArgs ? '保存并批准' : '批准执行'}
            </button>
          </div>
        </footer>
      </section>
    ) : null

}
