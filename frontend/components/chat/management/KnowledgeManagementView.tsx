'use client'

import { useState, type ChangeEvent, type MouseEvent, type Ref } from 'react'

import styles from '../../ChatInterface.module.css'
import { CreateKnowledgeBaseModal } from '../shared/CreateKnowledgeBaseModal'
import { Pagination } from '../shared/Pagination'
import type {
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeDocumentDetailResponse,
  KnowledgePage,
  ViewMode,
} from '../../chat-interface/types'
import { formatDateTime } from '../../chat-interface/utils'

interface KnowledgeManagementViewProps {
  knowledgePage: Exclude<KnowledgePage, 'users'>
  managementNotice: string
  managementError: string
  writeDisabled: boolean
  writeDisabledMessage: string
  knowledgeBaseTotal: number
  visibleChunkTotal: number
  knowledgeBases: KnowledgeBase[]
  selectedKnowledgeBaseId: string
  selectedKnowledgeBase: KnowledgeBase | null
  checkedKnowledgeBaseIds: string[]
  knowledgeBaseSearchInput: string
  knowledgeBasePage: number
  knowledgeBasePageTotal: number
  documents: KnowledgeDocument[]
  documentTotal: number
  documentPage: number
  documentPageTotal: number
  documentSearchInput: string
  checkedDocumentIds: string[]
  selectedDocumentDetail: KnowledgeDocumentDetailResponse | null
  documentChunkPage: number
  documentChunkPageTotal: number
  knowledgeBaseName: string
  knowledgeBaseDescription: string
  showCreateKnowledgeBaseModal: boolean
  savingKnowledgeBase: boolean
  uploadingDocuments: boolean
  deletingBulk: boolean
  loadingDocuments: boolean
  loadingDocumentDetail: boolean
  uploadInputRef: Ref<HTMLInputElement>
  onNavigateTo: (
    viewMode: ViewMode,
    knowledgePage?: KnowledgePage,
    replace?: boolean
  ) => void
  onUpdateKnowledgeBase: (
    knowledgeBaseId: string,
    name: string,
    description: string
  ) => Promise<void>
  onDeleteKnowledgeBase: (knowledgeBaseId?: string) => void | Promise<void>
  onOpenUploadDialog: () => void
  onHandleUploadFiles: (event: ChangeEvent<HTMLInputElement>) => void | Promise<void>
  onDocumentSearchInputChange: (value: string) => void
  onDocumentPageChange: (page: number | ((prev: number) => number)) => void
  onDocumentSearchChange: (value: string) => void
  onBulkDeleteDocuments: () => void | Promise<void>
  onToggleDocumentChecked: (
    documentId: string,
    event: MouseEvent<HTMLButtonElement | HTMLInputElement>
  ) => void
  onOpenDocumentDetail: (document: KnowledgeDocument) => void
  onRenameDocument: (document: KnowledgeDocument) => void | Promise<void>
  onDeleteDocument: (documentId?: string, documentName?: string) => void | Promise<void>
  onDocumentChunkPageChange: (page: number | ((prev: number) => number)) => void
  onKnowledgeBaseSearchInputChange: (value: string) => void
  onKnowledgeBasePageChange: (page: number | ((prev: number) => number)) => void
  onKnowledgeBaseSearchChange: (value: string) => void
  onBulkDeleteKnowledgeBases: () => void | Promise<void>
  onShowCreateKnowledgeBaseModalChange: (open: boolean) => void
  onToggleKnowledgeBaseChecked: (
    knowledgeBaseId: string,
    event: MouseEvent<HTMLButtonElement | HTMLInputElement>
  ) => void
  onOpenKnowledgeBaseLibrary: (knowledgeBase: KnowledgeBase) => void
  onKnowledgeBaseNameChange: (value: string) => void
  onKnowledgeBaseDescriptionChange: (value: string) => void
  onCreateKnowledgeBase: () => void | Promise<void>
}

export function KnowledgeManagementView({
  knowledgePage,
  managementNotice,
  managementError,
  writeDisabled,
  writeDisabledMessage,
  knowledgeBaseTotal,
  knowledgeBases,
  selectedKnowledgeBase,
  checkedKnowledgeBaseIds,
  knowledgeBaseSearchInput,
  knowledgeBasePage,
  knowledgeBasePageTotal,
  documents,
  documentTotal,
  documentPage,
  documentPageTotal,
  documentSearchInput,
  checkedDocumentIds,
  selectedDocumentDetail,
  documentChunkPage,
  documentChunkPageTotal,
  knowledgeBaseName,
  knowledgeBaseDescription,
  showCreateKnowledgeBaseModal,
  savingKnowledgeBase,
  uploadingDocuments,
  deletingBulk,
  loadingDocuments,
  loadingDocumentDetail,
  uploadInputRef,
  onNavigateTo,
  onUpdateKnowledgeBase,
  onDeleteKnowledgeBase,
  onOpenUploadDialog,
  onHandleUploadFiles,
  onDocumentSearchInputChange,
  onDocumentPageChange,
  onDocumentSearchChange,
  onBulkDeleteDocuments,
  onToggleDocumentChecked,
  onOpenDocumentDetail,
  onRenameDocument,
  onDeleteDocument,
  onDocumentChunkPageChange,
  onKnowledgeBaseSearchInputChange,
  onKnowledgeBasePageChange,
  onKnowledgeBaseSearchChange,
  onBulkDeleteKnowledgeBases,
  onShowCreateKnowledgeBaseModalChange,
  onToggleKnowledgeBaseChecked,
  onOpenKnowledgeBaseLibrary,
  onKnowledgeBaseNameChange,
  onKnowledgeBaseDescriptionChange,
  onCreateKnowledgeBase,
}: KnowledgeManagementViewProps) {
  const [editingKnowledgeBase, setEditingKnowledgeBase] =
    useState<KnowledgeBase | null>(null)
  const [editingKnowledgeBaseName, setEditingKnowledgeBaseName] = useState('')
  const [editingKnowledgeBaseDescription, setEditingKnowledgeBaseDescription] =
    useState('')
  const [updatingKnowledgeBase, setUpdatingKnowledgeBase] = useState(false)

  /**
   * 打开知识库编辑弹窗。
   *
   * Args:
   *   knowledgeBase: 待编辑的知识库。
   */
  const openEditKnowledgeBaseModal = (knowledgeBase: KnowledgeBase) => {
    setEditingKnowledgeBase(knowledgeBase)
    setEditingKnowledgeBaseName(knowledgeBase.name)
    setEditingKnowledgeBaseDescription(knowledgeBase.description)
  }

  /**
   * 关闭知识库编辑弹窗。
   *
   * Args:
   *   无。
   */
  const closeEditKnowledgeBaseModal = () => {
    if (updatingKnowledgeBase) return
    setEditingKnowledgeBase(null)
  }

  /**
   * 提交知识库编辑内容。
   *
   * Args:
   *   无。
   */
  const submitKnowledgeBaseEdit = async () => {
    if (!editingKnowledgeBase || !editingKnowledgeBaseName.trim()) return

    setUpdatingKnowledgeBase(true)
    try {
      await onUpdateKnowledgeBase(
        editingKnowledgeBase.knowledge_base_id,
        editingKnowledgeBaseName,
        editingKnowledgeBaseDescription
      )
      setEditingKnowledgeBase(null)
    } catch {
      return
    } finally {
      setUpdatingKnowledgeBase(false)
    }
  }

  const renderDocumentDetailPage = () =>
    selectedDocumentDetail ? (
      <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace} ${styles.knowledgeWorkspace}`}>
        <header className={styles.extensionHeading}>
          <div><button type="button" className={styles.knowledgeBreadcrumb} onClick={() => onNavigateTo('knowledge', 'library-detail')}>{selectedDocumentDetail.knowledge_base.name} /</button><h2>{selectedDocumentDetail.document.display_name}</h2><p>查看原始文件信息和用于检索的文本切片。</p></div>
          <div className={styles.extensionHeadingActions}>
            <span className={styles.extensionCount}>{selectedDocumentDetail.total_chunks} 个切片</span>
            <button className={styles.extensionSecondaryButton} disabled={writeDisabled} onClick={() => void onRenameDocument(selectedDocumentDetail.document)}>重命名</button>
            <button className={styles.extensionDeleteButton} disabled={writeDisabled} onClick={() => void onDeleteDocument(selectedDocumentDetail.document.document_id, selectedDocumentDetail.document.display_name)}>删除文档</button>
          </div>
        </header>
        <div className={styles.knowledgeDocumentLayout}>
          <section className={styles.knowledgeFilePanel}>
            <div className={styles.managementHeader}>
              <h3>{selectedDocumentDetail.document.display_name}</h3>
              <span className={styles.managementMeta}>
                {loadingDocumentDetail
                  ? '加载中...'
                  : `${selectedDocumentDetail.total_chunks} 个切片`}
              </span>
            </div>
            <div className={styles.managementMetaPanel}>
              <span>所属知识库: {selectedDocumentDetail.knowledge_base.name}</span>
              <span>原始文件: {selectedDocumentDetail.document.file_name}</span>
              <span>
                文件大小: {Math.max(1, Math.round(selectedDocumentDetail.document.file_size / 1024))} KB
              </span>
              <span>切片数量: {selectedDocumentDetail.document.chunk_count}</span>
              <span>更新时间: {formatDateTime(selectedDocumentDetail.document.updated_at)}</span>
            </div>
          </section>

          <section className={styles.knowledgeChunksPanel}>
            <div className={styles.managementHeader}>
              <h3>切片详情</h3>
              <span className={styles.managementMeta}>
                第 {documentChunkPage} / {documentChunkPageTotal} 页
              </span>
            </div>
            <div className={styles.knowledgeChunksList}>
              {selectedDocumentDetail.chunks.length === 0 ? (
                <div className={styles.managementEmpty}>暂无切片数据</div>
              ) : (
                selectedDocumentDetail.chunks.map((chunk) => (
                  <article key={chunk.chunk_id} className={styles.knowledgeChunk}>
                    <div className={styles.managementListHeader}>
                      <strong>切片 #{chunk.segment_id || '-'}</strong>
                      <span>{chunk.chunk_id}</span>
                    </div>
                    <p className={styles.knowledgeChunkContent}>{chunk.content}</p>
                    <div className={styles.managementListMeta}>
                      <span>页码: {String(chunk.metadata.pages_number ?? '-')}</span>
                      <span>标题: {String(chunk.metadata.title ?? '-')}</span>
                    </div>
                  </article>
                ))
              )}
            </div>
            <Pagination
              page={documentChunkPage}
              pageTotal={documentChunkPageTotal}
              total={selectedDocumentDetail.total_chunks}
              onPrev={() => onDocumentChunkPageChange((prev) => Math.max(1, prev - 1))}
              onNext={() =>
                onDocumentChunkPageChange((prev) =>
                  Math.min(documentChunkPageTotal, prev + 1)
                )
              }
            />
          </section>
        </div>
      </div>
    ) : (
      <div className={styles.managementEmptyState}>
        <div className={styles.managementEmpty}>请先从知识库详情页选择一条文档。</div>
        <button
          className={styles.managementButton}
          onClick={() => onNavigateTo('knowledge', 'libraries')}
        >
          返回知识库
        </button>
      </div>
    )

  const renderLibraryDetailPage = () =>
    selectedKnowledgeBase ? (
      <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace} ${styles.knowledgeWorkspace}`}>
        <header className={styles.extensionHeading}>
          <div>
            <button type="button" className={styles.knowledgeBreadcrumb} onClick={() => onNavigateTo('knowledge', 'libraries')}>知识库 /</button>
            <h2>{selectedKnowledgeBase.name}</h2>
            <p className={styles.managementKnowledgeHeroDescription}>
              {selectedKnowledgeBase.description || '当前知识库暂无描述。'}
            </p>
          </div>
          <div className={styles.extensionHeadingActions}>
            <span className={styles.extensionCount}>{selectedKnowledgeBase.document_count} 文档 · {selectedKnowledgeBase.chunk_count} 切片</span>
            <button
              className={styles.extensionPrimaryButton}
              disabled={uploadingDocuments || writeDisabled}
              onClick={onOpenUploadDialog}
            >
              {uploadingDocuments ? '上传中...' : '＋ 上传文件'}
            </button>
            <input
              ref={uploadInputRef}
              className={styles.hiddenUpload}
              type="file"
              multiple
              onChange={(event) => void onHandleUploadFiles(event)}
            />
          </div>
        </header>

        <section
          className={styles.knowledgeDetailSection}
        >
          <div className={styles.managementHeader}>
            <div className={styles.managementKnowledgeSectionTitle}>
              <h3>知识文件</h3>
              <p>{formatDateTime(selectedKnowledgeBase.updated_at)} 更新</p>
            </div>
            <span className={styles.managementMeta}>
              {loadingDocuments ? '加载中...' : `共 ${documentTotal} 条`}
            </span>
          </div>
          <div className={styles.knowledgeToolbar}>
            <div className={styles.managementSearchGroup}>
              <input
                className={styles.knowledgeSearchInput}
                value={documentSearchInput}
                onChange={(event) => onDocumentSearchInputChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    onDocumentPageChange(1)
                    onDocumentSearchChange(documentSearchInput.trim())
                  }
                }}
                placeholder="搜索知识文件"
              />
              <button
                className={styles.extensionSecondaryButton}
                onClick={() => {
                  onDocumentPageChange(1)
                  onDocumentSearchChange(documentSearchInput.trim())
                }}
              >
                搜索
              </button>
            </div>
            <button
              className={styles.extensionDeleteButton}
              disabled={
                checkedDocumentIds.length === 0 || deletingBulk || writeDisabled
              }
              onClick={() => void onBulkDeleteDocuments()}
            >
              批量删除
            </button>
          </div>

          <div className={styles.knowledgeList}>
            {documents.length === 0 ? (
              <div className={styles.extensionEmpty}><strong>还没有知识文件</strong><span>上传 PDF、DOCX 等文件后会自动完成切片和索引。</span><button className={styles.extensionTextButton} disabled={uploadingDocuments || writeDisabled} onClick={onOpenUploadDialog}>上传文件</button></div>
            ) : documents.map((document) => (
              <div className={styles.knowledgeRow} key={document.document_id}>
                <label className={styles.knowledgeCheckbox} onClick={(event) => onToggleDocumentChecked(document.document_id, event as unknown as MouseEvent<HTMLButtonElement | HTMLInputElement>)}><input type="checkbox" aria-label={`选择文件 ${document.display_name}`} checked={checkedDocumentIds.includes(document.document_id)} onChange={() => undefined} /></label>
                <button type="button" className={styles.knowledgeRowPrimary} onClick={() => onOpenDocumentDetail(document)}><span className={styles.knowledgeDocumentMark} aria-hidden="true">{document.file_name.split('.').pop()?.slice(0, 3).toUpperCase() || 'DOC'}</span><span className={styles.knowledgeRowText}><strong>{document.display_name}</strong><small>{document.file_name}</small></span></button>
                <span className={styles.knowledgeRowMetric}>{document.chunk_count} 切片 · {Math.max(1, Math.round(document.file_size / 1024))} KB</span>
                <span className={styles.knowledgeRowDate}>{formatDateTime(document.updated_at)}</span>
                <div className={styles.knowledgeRowActions}><button className={styles.extensionTextButton} disabled={writeDisabled} onClick={() => void onRenameDocument(document)}>重命名</button><button className={styles.extensionDeleteButton} disabled={writeDisabled} onClick={() => void onDeleteDocument(document.document_id, document.display_name)}>删除</button></div>
              </div>
            ))}
          </div>
          <div className={styles.managementKnowledgePagination}>
            <Pagination
              page={documentPage}
              pageTotal={documentPageTotal}
              total={documentTotal}
              onPrev={() => onDocumentPageChange((prev) => Math.max(1, prev - 1))}
              onNext={() =>
                onDocumentPageChange((prev) => Math.min(documentPageTotal, prev + 1))
              }
            />
          </div>
        </section>
      </div>
    ) : (
      <div className={styles.managementEmptyState}>
        <div className={styles.managementEmpty}>请先从知识库列表选择一个知识库。</div>
        <button
          className={styles.managementButton}
          onClick={() => onNavigateTo('knowledge', 'libraries')}
        >
          返回知识库列表
        </button>
      </div>
    )

  const renderLibrariesPage = () => (
    <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace} ${styles.knowledgeWorkspace}`}>
      <header className={styles.extensionHeading}>
        <div>
          <span className={styles.extensionEyebrow}>KNOWLEDGE / LIBRARIES</span>
          <h2>知识库</h2>
          <p>集中管理用于检索和问答的资料。</p>
        </div>
        <div className={styles.extensionHeadingActions}>
          <span className={styles.extensionCount}>{knowledgeBaseTotal} 个知识库</span>
          <button
            type="button"
            className={styles.extensionPrimaryButton}
            disabled={writeDisabled}
            onClick={() => onShowCreateKnowledgeBaseModalChange(true)}
          >
            ＋ 新建知识库
          </button>
        </div>
      </header>

      <section className={styles.knowledgeToolbar}>
        <div className={styles.managementSearchGroup}>
          <input
            className={styles.knowledgeSearchInput}
            value={knowledgeBaseSearchInput}
            onChange={(event) => onKnowledgeBaseSearchInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                onKnowledgeBasePageChange(1)
                onKnowledgeBaseSearchChange(knowledgeBaseSearchInput.trim())
              }
            }}
            placeholder="搜索知识库名称或描述"
          />
          <button
            className={styles.extensionSecondaryButton}
            onClick={() => {
              onKnowledgeBasePageChange(1)
              onKnowledgeBaseSearchChange(knowledgeBaseSearchInput.trim())
            }}
          >
            搜索
          </button>
        </div>

        <div className={styles.managementKnowledgeToolbarActions}>
          <button
            className={styles.extensionDeleteButton}
            disabled={
              checkedKnowledgeBaseIds.length === 0 || deletingBulk || writeDisabled
            }
            onClick={() => void onBulkDeleteKnowledgeBases()}
          >
            批量删除
          </button>
        </div>
      </section>

      <div className={styles.knowledgeList}>
        {knowledgeBases.length === 0 ? (
          <div className={styles.extensionEmpty}><strong>还没有知识库</strong><span>新建知识库后可以集中上传和管理资料。</span><button type="button" className={styles.extensionTextButton} disabled={writeDisabled} onClick={() => onShowCreateKnowledgeBaseModalChange(true)}>新建知识库</button></div>
        ) : knowledgeBases.map((knowledgeBase) => (
          <div className={styles.knowledgeRow} key={knowledgeBase.knowledge_base_id}>
            <label className={styles.knowledgeCheckbox} onClick={(event) => onToggleKnowledgeBaseChecked(knowledgeBase.knowledge_base_id, event as unknown as MouseEvent<HTMLButtonElement | HTMLInputElement>)}>
              <input type="checkbox" aria-label={`选择知识库 ${knowledgeBase.name}`} checked={checkedKnowledgeBaseIds.includes(knowledgeBase.knowledge_base_id)} onChange={() => undefined} />
            </label>
            <button type="button" className={styles.knowledgeRowPrimary} onClick={() => onOpenKnowledgeBaseLibrary(knowledgeBase)}>
              <span className={styles.knowledgeIdentityMark} aria-hidden="true">库</span>
              <span className={styles.knowledgeRowText}><strong>{knowledgeBase.name}</strong><small>{knowledgeBase.description || '暂无描述'}</small></span>
            </button>
            <span className={styles.knowledgeRowMetric}>{knowledgeBase.document_count} 文档 · {knowledgeBase.chunk_count} 切片</span>
            <span className={styles.knowledgeRowDate}>{formatDateTime(knowledgeBase.updated_at)}</span>
            <div className={styles.knowledgeRowActions}>
              <button type="button" className={styles.extensionTextButton} disabled={writeDisabled || savingKnowledgeBase} onClick={() => openEditKnowledgeBaseModal(knowledgeBase)}>编辑</button>
              <button type="button" className={styles.extensionDeleteButton} disabled={writeDisabled || savingKnowledgeBase} onClick={() => void onDeleteKnowledgeBase(knowledgeBase.knowledge_base_id)}>删除</button>
            </div>
          </div>
        ))}
      </div>
      <div className={styles.managementKnowledgePagination}>
        <Pagination
          page={knowledgeBasePage}
          pageTotal={knowledgeBasePageTotal}
          total={knowledgeBaseTotal}
          onPrev={() => onKnowledgeBasePageChange((prev) => Math.max(1, prev - 1))}
          onNext={() =>
            onKnowledgeBasePageChange((prev) =>
              Math.min(knowledgeBasePageTotal, prev + 1)
            )
          }
        />
      </div>
    </div>
  )

  const renderKnowledgePage = () => {
    if (knowledgePage === 'document-detail') return renderDocumentDetailPage()
    if (knowledgePage === 'library-detail') return renderLibraryDetailPage()
    return renderLibrariesPage()
  }

  return (
    <>
      <div
        className={`${styles.managementPage} ${styles.managementKnowledgePage}`}
      >
        <div className={styles.managementNoticeRow}>
          {writeDisabled ? (
            <div className={styles.managementNotice}>{writeDisabledMessage}</div>
          ) : null}
          {managementNotice ? (
            <div className={styles.managementNotice}>{managementNotice}</div>
          ) : null}
          {managementError ? <div className={styles.managementError}>{managementError}</div> : null}
        </div>
        {renderKnowledgePage()}
      </div>

      <CreateKnowledgeBaseModal
        open={showCreateKnowledgeBaseModal}
        knowledgeBaseName={knowledgeBaseName}
        knowledgeBaseDescription={knowledgeBaseDescription}
        savingKnowledgeBase={savingKnowledgeBase}
        createDisabled={writeDisabled}
        disabledMessage={writeDisabledMessage}
        onClose={() => onShowCreateKnowledgeBaseModalChange(false)}
        onNameChange={onKnowledgeBaseNameChange}
        onDescriptionChange={onKnowledgeBaseDescriptionChange}
        onCreate={onCreateKnowledgeBase}
      />
      <CreateKnowledgeBaseModal
        mode="edit"
        open={editingKnowledgeBase !== null}
        knowledgeBaseName={editingKnowledgeBaseName}
        knowledgeBaseDescription={editingKnowledgeBaseDescription}
        savingKnowledgeBase={updatingKnowledgeBase}
        createDisabled={writeDisabled}
        disabledMessage={writeDisabledMessage}
        onClose={closeEditKnowledgeBaseModal}
        onNameChange={setEditingKnowledgeBaseName}
        onDescriptionChange={setEditingKnowledgeBaseDescription}
        onCreate={submitKnowledgeBaseEdit}
      />
    </>
  )
}
