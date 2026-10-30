import styles from './InterruptPanel.module.css'
import { isRecord, formatArgLabel, type InterruptArgPath } from './utils'

interface InterruptArgFieldsProps {
  value: unknown
  path: InterruptArgPath
  label?: string
  disabled: boolean
  inputRef?: (element: HTMLInputElement | HTMLTextAreaElement | null) => void
  onChange: (path: InterruptArgPath, value: unknown) => void
}

/**
 * 按数据类型递归展示和编辑审批参数。
 *
 * Args:
 *   value: 当前参数值。
 *   path: 参数在原对象中的路径。
 *   label: 参数名称。
 *   disabled: 是否只读。
 *   inputRef: 首个可编辑输入框的引用。
 *   onChange: 参数值变更回调。
 */
export function InterruptArgFields({
  value,
  path,
  label,
  disabled,
  inputRef,
  onChange,
}: InterruptArgFieldsProps) {
  if (Array.isArray(value)) {
    return (
      <div className={styles.interruptArgGroup}>
        {label && <div className={styles.interruptArgGroupLabel}>{label}</div>}
        {value.length > 0 ? (
          value.map((item, index) => (
            <InterruptArgFields
              key={`${path.join('.')}.${index}`}
              value={item}
              path={[...path, index]}
              label={formatArgLabel(index)}
              disabled={disabled}
              onChange={onChange}
            />
          ))
        ) : (
          <span className={styles.interruptArgEmpty}>空列表</span>
        )}
      </div>
    )
  }

  if (isRecord(value)) {
    const entries = Object.entries(value)

    return (
      <div className={styles.interruptArgGroup}>
        {label && <div className={styles.interruptArgGroupLabel}>{label}</div>}
        {entries.length > 0 ? (
          entries.map(([key, item], index) => (
            <InterruptArgFields
              key={`${path.join('.')}.${key}`}
              value={item}
              path={[...path, key]}
              label={formatArgLabel(key)}
              disabled={disabled}
              inputRef={path.length === 0 && index === 0 ? inputRef : undefined}
              onChange={onChange}
            />
          ))
        ) : (
          <span className={styles.interruptArgEmpty}>空对象</span>
        )}
      </div>
    )
  }

  if (typeof value === 'boolean') {
    return (
      <label className={styles.interruptFormField}>
        <span className={styles.interruptFieldLabel}>{label}</span>
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptCheckbox}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={(event) => onChange(path, event.currentTarget.checked)}
        />
      </label>
    )
  }

  if (typeof value === 'number') {
    return (
      <label className={styles.interruptFormField}>
        <span className={styles.interruptFieldLabel}>{label}</span>
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptInput}
          type="number"
          value={Number.isFinite(value) ? value : ''}
          disabled={disabled}
          onChange={(event) => {
            const raw = event.currentTarget.value
            onChange(path, raw === '' ? null : Number(raw))
          }}
        />
      </label>
    )
  }

  const textValue = value == null ? '' : String(value)
  const isLongText = textValue.length > 80 || textValue.includes('\n')

  return (
    <label className={styles.interruptFormField}>
      <span className={styles.interruptFieldLabel}>{label}</span>
      {disabled ? <span className={styles.interruptReadValue}>{textValue || '—'}</span> : isLongText ? (
        <textarea
          ref={inputRef as ((element: HTMLTextAreaElement | null) => void) | undefined}
          className={styles.interruptInput}
          value={textValue}
          disabled={disabled}
          rows={4}
          onChange={(event) => onChange(path, event.currentTarget.value)}
        />
      ) : (
        <input
          ref={inputRef as ((element: HTMLInputElement | null) => void) | undefined}
          className={styles.interruptInput}
          type="text"
          value={textValue}
          disabled={disabled}
          onChange={(event) => onChange(path, event.currentTarget.value)}
        />
      )}
    </label>
  )
}

