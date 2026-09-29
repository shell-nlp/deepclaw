'use client'

import styles from '../../ChatInterface.module.css'
import type { ChatModeOption } from '../../chat-interface/types'

interface AgentModeSwitcherProps {
  options: ChatModeOption[]
  value: string
  disabled?: boolean
  onChange: (optionId: string) => void
}

/**
 * 渲染顶部状态栏的会话模式切换器。
 *
 * Args:
 *   options: 可选模式列表，含智能体 ID、展示名与是否知识库模式。
 *   value: 当前模式对应的智能体 ID。
 *   disabled: 是否禁用切换，例如请求处理中。
 *   onChange: 模式切换回调，参数为目标智能体 ID。
 */
export function AgentModeSwitcher({
  options,
  value,
  disabled = false,
  onChange,
}: AgentModeSwitcherProps) {
  if (options.length === 0) return null

  return (
    <div className={styles.modeSwitcher} role="radiogroup" aria-label="会话模式">
      {options.map((option) => {
        const active = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={active}
            className={active ? styles.modeOptionActive : styles.modeOption}
            disabled={disabled}
            title={option.description || option.label}
            onClick={() => {
              if (!active) onChange(option.id)
            }}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
