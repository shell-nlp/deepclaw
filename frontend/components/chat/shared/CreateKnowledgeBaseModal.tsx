import styles from '../../ChatInterface.module.css'

interface CreateKnowledgeBaseModalProps {
  mode?: 'create' | 'edit'
  open: boolean
  knowledgeBaseName: string
  knowledgeBaseDescription: string
  savingKnowledgeBase: boolean
  createDisabled: boolean
  disabledMessage: string
  onClose: () => void
  onNameChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  onCreate: () => void | Promise<void>
}

export function CreateKnowledgeBaseModal({
  mode = 'create',
  open,
  knowledgeBaseName,
  knowledgeBaseDescription,
  savingKnowledgeBase,
  createDisabled,
  disabledMessage,
  onClose,
  onNameChange,
  onDescriptionChange,
  onCreate,
}: CreateKnowledgeBaseModalProps) {
  if (!open) return null
  const isEditing = mode === 'edit'

  return (
    <div className={styles.extensionDialogOverlay} onClick={onClose}>
      <div className={`${styles.extensionDialog} ${styles.knowledgeModal}`} role="dialog" aria-modal="true" aria-labelledby="knowledge-modal-title" onClick={(event) => event.stopPropagation()}>
        <div className={styles.extensionDialogHeader}>
          <div><span className={styles.extensionEyebrow}>KNOWLEDGE / {isEditing ? 'EDIT' : 'NEW'}</span><h3 id="knowledge-modal-title">{isEditing ? '编辑知识库' : '新建知识库'}</h3></div>
          <button
            type="button"
            className={styles.extensionIconButton}
            onClick={onClose}
            aria-label="关闭弹窗"
          >
            ×
          </button>
        </div>
        <div className={styles.managementForm}>
          {createDisabled ? (
            <div className={styles.managementNotice}>{disabledMessage}</div>
          ) : null}
          <label className={styles.knowledgeModalLabel}>知识库名称<input
            className={styles.managementInput}
            value={knowledgeBaseName}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder="知识库名称"
            autoFocus
            disabled={createDisabled}
          /></label>
          <label className={styles.knowledgeModalLabel}>描述<input
            className={styles.managementInput}
            value={knowledgeBaseDescription}
            onChange={(event) => onDescriptionChange(event.target.value)}
            placeholder="知识库描述"
            disabled={createDisabled}
          /></label>
          <div className={styles.extensionDialogActions}>
            <button
              type="button"
              className={styles.extensionSecondaryButton}
              onClick={onClose}
            >
              取消
            </button>
            <button
              className={styles.extensionPrimaryButton}
              disabled={savingKnowledgeBase || createDisabled || !knowledgeBaseName.trim()}
              onClick={() => void onCreate()}
            >
              {isEditing ? '保存修改' : '创建知识库'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
