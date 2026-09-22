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
    <div className={styles.managementModalOverlay} onClick={onClose}>
      <div className={styles.managementModal} onClick={(event) => event.stopPropagation()}>
        <div className={styles.managementHeader}>
          <h3>{isEditing ? '编辑知识库' : '新建知识库'}</h3>
          <button
            type="button"
            className={styles.managementModalClose}
            onClick={onClose}
          >
            关闭
          </button>
        </div>
        <div className={styles.managementForm}>
          {createDisabled ? (
            <div className={styles.managementNotice}>{disabledMessage}</div>
          ) : null}
          <input
            className={styles.managementInput}
            value={knowledgeBaseName}
            onChange={(event) => onNameChange(event.target.value)}
            placeholder="知识库名称"
            autoFocus
            disabled={createDisabled}
          />
          <input
            className={styles.managementInput}
            value={knowledgeBaseDescription}
            onChange={(event) => onDescriptionChange(event.target.value)}
            placeholder="知识库描述"
            disabled={createDisabled}
          />
          <div className={styles.managementToolbar}>
            <button
              className={styles.managementButton}
              disabled={savingKnowledgeBase || createDisabled}
              onClick={() => void onCreate()}
            >
              {isEditing ? '保存修改' : '创建知识库'}
            </button>
            <button
              type="button"
              className={styles.managementMinorButton}
              onClick={onClose}
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
