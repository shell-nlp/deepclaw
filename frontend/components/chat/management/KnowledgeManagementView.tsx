'use client'

import { useState, type ChangeEvent, type MouseEvent, type Ref } from 'react'

import styles from '../../ChatInterface.module.css'
import { SidebarIcon } from '../shared/BrandIcons'
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

type KnowledgeBaseViewMode = 'card' | 'list'

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
  visibleChunkTotal,
  knowledgeBases,
  selectedKnowledgeBaseId,
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
  const [knowledgeBaseViewMode, setKnowledgeBaseViewMode] =
    useState<KnowledgeBaseViewMode>('card')
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
      <div className={styles.managementWorkspace}>
        <section className={styles.managementHero}>
          <div className={styles.managementHeroCopy}>
            <span className={styles.managementHeroEyebrow}>Document Detail</span>
            <h2>查看文档切片与检索元数据</h2>
            <p>核对原始文件、切片数量和更新时间，再逐条检查用于检索的文本片段。</p>
          </div>
        </section>
        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
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
            <div className={styles.managementToolbar}>
              <button
                className={styles.managementMinorButton}
                onClick={() => onNavigateTo('knowledge', 'library-detail')}
              >
                返回知识库详情
              </button>
              <button
                className={styles.managementMinorButton}
                disabled={writeDisabled}
                onClick={() => void onRenameDocument(selectedDocumentDetail.document)}
              >
                重命名
              </button>
              <button
                className={styles.managementDangerButton}
                disabled={writeDisabled}
                onClick={() =>
                  void onDeleteDocument(
                    selectedDocumentDetail.document.document_id,
                    selectedDocumentDetail.document.display_name
                  )
                }
              >
                删除文档
              </button>
            </div>
          </section>

          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>切片详情</h3>
              <span className={styles.managementMeta}>
                第 {documentChunkPage} / {documentChunkPageTotal} 页
              </span>
            </div>
            <div className={styles.managementList}>
              {selectedDocumentDetail.chunks.length === 0 ? (
                <div className={styles.managementEmpty}>暂无切片数据</div>
              ) : (
                selectedDocumentDetail.chunks.map((chunk) => (
                  <div key={chunk.chunk_id} className={styles.managementListItemStatic}>
                    <div className={styles.managementListHeader}>
                      <strong>切片 #{chunk.segment_id || '-'}</strong>
                      <span>{chunk.chunk_id}</span>
                    </div>
                    <p className={styles.managementDescription}>{chunk.content}</p>
                    <div className={styles.managementListMeta}>
                      <span>页码: {String(chunk.metadata.pages_number ?? '-')}</span>
                      <span>标题: {String(chunk.metadata.title ?? '-')}</span>
                    </div>
                  </div>
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
      <div className={styles.managementWorkspace}>
        <section className={styles.managementHero}>
          <div className={styles.managementHeroCopy}>
            <span className={styles.managementHeroEyebrow}>Knowledge Base</span>
            <h2>{selectedKnowledgeBase.name}</h2>
            <p className={styles.managementKnowledgeHeroDescription}>
              {selectedKnowledgeBase.description || '当前知识库暂无描述。'}
            </p>
            <div className={styles.managementKnowledgeHeroMeta}>
              <span>{selectedKnowledgeBase.document_count} 文档</span>
              <span>{selectedKnowledgeBase.chunk_count} 切片</span>
              <span>{formatDateTime(selectedKnowledgeBase.updated_at)} 更新</span>
            </div>
          </div>
          <div className={styles.managementHeroActions}>
            <button
              className={styles.managementMinorButton}
              onClick={() => onNavigateTo('knowledge', 'libraries')}
            >
              返回知识库列表
            </button>
            <button
              className={styles.managementButton}
              disabled={uploadingDocuments || writeDisabled}
              onClick={onOpenUploadDialog}
            >
              {uploadingDocuments ? '上传中...' : '上传知识文件'}
            </button>
            <input
              ref={uploadInputRef}
              className={styles.hiddenUpload}
              type="file"
              multiple
              onChange={(event) => void onHandleUploadFiles(event)}
            />
          </div>
        </section>

        <section
          className={`${styles.managementCard} ${styles.managementKnowledgeDetailSection}`}
        >
          <div className={styles.managementHeader}>
            <div className={styles.managementKnowledgeSectionTitle}>
              <h3>知识列表</h3>
              <p>上传并管理当前知识库中的文档</p>
            </div>
            <span className={styles.managementMeta}>
              {loadingDocuments ? '加载中...' : `共 ${documentTotal} 条`}
            </span>
          </div>
          <div className={styles.managementToolbar}>
            <div className={styles.managementSearchGroup}>
              <input
                className={styles.managementInput}
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
                className={styles.managementButton}
                onClick={() => {
                  onDocumentPageChange(1)
                  onDocumentSearchChange(documentSearchInput.trim())
                }}
              >
                搜索
              </button>
            </div>
            <button
              className={styles.managementDangerButton}
              disabled={
                checkedDocumentIds.length === 0 || deletingBulk || writeDisabled
              }
              onClick={() => void onBulkDeleteDocuments()}
            >
              批量删除
            </button>
          </div>

          <div className={styles.managementCardGrid}>
            {documents.length === 0 ? (
              <div
                className={`${styles.managementEmpty} ${styles.managementKnowledgeEmpty}`}
              >
                <strong>还没有知识文档</strong>
                <span>上传 PDF、DOCX 等文件后，系统会自动完成切片和索引。</span>
                <button
                  type="button"
                  className={styles.managementButton}
                  disabled={uploadingDocuments || writeDisabled}
                  onClick={onOpenUploadDialog}
                >
                  {uploadingDocuments ? '上传中...' : '上传知识文件'}
                </button>
              </div>
            ) : (
              documents.map((document) => (
                <div key={document.document_id} className={styles.managementTileCard}>
                  <div className={styles.managementListHeader}>
                    <label
                      className={styles.managementCheckbox}
                      onClick={(event) =>
                        onToggleDocumentChecked(
                          document.document_id,
                          event as unknown as MouseEvent<
                            HTMLButtonElement | HTMLInputElement
                          >
                        )
                      }
                    >
                      <input
                        type="checkbox"
                        checked={checkedDocumentIds.includes(document.document_id)}
                        onChange={() => undefined}
                      />
                    </label>
                    <strong>{document.display_name}</strong>
                    <span>{document.chunk_count} 切片</span>
                  </div>
                  <p className={styles.managementDescription}>
                    原始文件: {document.file_name}
                  </p>
                  <div className={styles.managementListMeta}>
                    <span>{Math.max(1, Math.round(document.file_size / 1024))} KB</span>
                    <span>{formatDateTime(document.updated_at)}</span>
                  </div>
                  <div className={styles.managementActionRow}>
                    <button
                      className={styles.managementButton}
                      onClick={() => onOpenDocumentDetail(document)}
                    >
                      查看详情
                    </button>
                    <button
                      className={styles.managementMinorButton}
                      disabled={writeDisabled}
                      onClick={() => void onRenameDocument(document)}
                    >
                      重命名
                    </button>
                    <button
                      className={styles.managementDangerMinorButton}
                      disabled={writeDisabled}
                      onClick={() =>
                        void onDeleteDocument(
                          document.document_id,
                          document.display_name
                        )
                      }
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))
            )}
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
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>Knowledge Bases</span>
          <h2>知识库</h2>
        </div>
        <div className={styles.managementHeroActions}>
          <button
            type="button"
            className={styles.managementButton}
            disabled={writeDisabled}
            onClick={() => onShowCreateKnowledgeBaseModalChange(true)}
          >
            新建知识库
          </button>
        </div>
      </section>

      <section className={styles.managementKnowledgeToolbar}>
        <div className={styles.managementSearchGroup}>
          <input
            className={styles.managementInput}
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
            className={styles.managementButton}
            onClick={() => {
              onKnowledgeBasePageChange(1)
              onKnowledgeBaseSearchChange(knowledgeBaseSearchInput.trim())
            }}
          >
            搜索
          </button>
        </div>

        <div className={styles.managementKnowledgeToolbarActions}>
          <div
            className={styles.managementViewToggle}
            role="group"
            aria-label="知识库展示方式"
          >
            <button
              type="button"
              className={`${styles.managementViewToggleButton} ${
                knowledgeBaseViewMode === 'card'
                  ? styles.managementViewToggleButtonActive
                  : ''
              }`}
              aria-pressed={knowledgeBaseViewMode === 'card'}
              onClick={() => setKnowledgeBaseViewMode('card')}
            >
              卡片
            </button>
            <button
              type="button"
              className={`${styles.managementViewToggleButton} ${
                knowledgeBaseViewMode === 'list'
                  ? styles.managementViewToggleButtonActive
                  : ''
              }`}
              aria-pressed={knowledgeBaseViewMode === 'list'}
              onClick={() => setKnowledgeBaseViewMode('list')}
            >
              列表
            </button>
          </div>

          <button
            className={styles.managementDangerButton}
            disabled={
              checkedKnowledgeBaseIds.length === 0 || deletingBulk || writeDisabled
            }
            onClick={() => void onBulkDeleteKnowledgeBases()}
          >
            批量删除
          </button>
        </div>
      </section>

      {knowledgeBaseViewMode === 'card' ? (
        <div className={styles.managementKnowledgeGrid}>
          {knowledgeBases.length === 0 ? (
            <div
              className={`${styles.managementEmpty} ${styles.managementKnowledgeEmpty}`}
            >
              <strong>还没有知识库</strong>
              <span>创建知识库后，可以集中上传和管理资料。</span>
              <button
                type="button"
                className={styles.managementButton}
                disabled={writeDisabled}
                onClick={() => onShowCreateKnowledgeBaseModalChange(true)}
              >
                新建知识库
              </button>
            </div>
          ) : (
            knowledgeBases.map((knowledgeBase) => (
              <article
                key={knowledgeBase.knowledge_base_id}
                className={`${styles.managementKnowledgeCard} ${
                  selectedKnowledgeBaseId === knowledgeBase.knowledge_base_id
                    ? styles.managementKnowledgeCardActive
                    : ''
                }`}
              >
                <div className={styles.managementKnowledgeCardHeader}>
                  <label
                    className={styles.managementCheckbox}
                    onClick={(event) =>
                      onToggleKnowledgeBaseChecked(
                        knowledgeBase.knowledge_base_id,
                        event as unknown as MouseEvent<
                          HTMLButtonElement | HTMLInputElement
                        >
                      )
                    }
                  >
                    <input
                      type="checkbox"
                      aria-label={`选择知识库 ${knowledgeBase.name}`}
                      checked={checkedKnowledgeBaseIds.includes(
                        knowledgeBase.knowledge_base_id
                      )}
                      onChange={() => undefined}
                    />
                  </label>
                  <div className={styles.managementKnowledgeCardIdentity}>
                    <span className={styles.managementKnowledgeCardIcon}>
                      <SidebarIcon name="knowledge" />
                    </span>
                    <div className={styles.managementKnowledgeCardTitle}>
                      <span>Knowledge Base</span>
                      <h3>{knowledgeBase.name}</h3>
                    </div>
                  </div>
                  <div className={styles.managementKnowledgeCardActions}>
                    <button
                      type="button"
                      className={styles.managementKnowledgeAction}
                      disabled={writeDisabled || savingKnowledgeBase}
                      onClick={() => openEditKnowledgeBaseModal(knowledgeBase)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className={styles.managementKnowledgeDangerAction}
                      disabled={writeDisabled || savingKnowledgeBase}
                      onClick={() =>
                        void onDeleteKnowledgeBase(knowledgeBase.knowledge_base_id)
                      }
                    >
                      删除
                    </button>
                  </div>
                </div>

                <p className={styles.managementKnowledgeDescription}>
                  {knowledgeBase.description || '暂无描述'}
                </p>

                <div className={styles.managementKnowledgeCardFooter}>
                  <div className={styles.managementKnowledgeCardMeta}>
                    <span>{knowledgeBase.document_count} 文档</span>
                    <span>{formatDateTime(knowledgeBase.updated_at)} 更新</span>
                  </div>
                  <button
                    type="button"
                    className={styles.managementMinorButton}
                    onClick={() => onOpenKnowledgeBaseLibrary(knowledgeBase)}
                  >
                    打开知识库
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      ) : (
        <div className={styles.managementDataList}>
          {knowledgeBases.length === 0 ? (
            <div className={styles.managementEmpty}>暂无知识库。</div>
          ) : (
            knowledgeBases.map((knowledgeBase) => (
              <div
                key={knowledgeBase.knowledge_base_id}
                className={`${styles.managementDataRow} ${
                  selectedKnowledgeBaseId === knowledgeBase.knowledge_base_id
                    ? styles.managementListItemActive
                    : ''
                }`}
              >
                <div className={styles.managementDataPrimary}>
                  <div className={styles.managementDataTitle}>
                    <label
                      className={styles.managementCheckbox}
                      onClick={(event) =>
                        onToggleKnowledgeBaseChecked(
                          knowledgeBase.knowledge_base_id,
                          event as unknown as MouseEvent<
                            HTMLButtonElement | HTMLInputElement
                          >
                        )
                      }
                    >
                      <input
                        type="checkbox"
                        aria-label={`选择知识库 ${knowledgeBase.name}`}
                        checked={checkedKnowledgeBaseIds.includes(
                          knowledgeBase.knowledge_base_id
                        )}
                        onChange={() => undefined}
                      />
                    </label>
                    <strong>{knowledgeBase.name}</strong>
                  </div>
                  <span className={styles.managementDataDescription}>
                    {knowledgeBase.description || '暂无描述'}
                  </span>
                </div>

                <div className={styles.managementDataMetrics}>
                  <span>{knowledgeBase.document_count} 文档</span>
                  <span>{formatDateTime(knowledgeBase.updated_at)}</span>
                </div>

                <div className={styles.managementDataActions}>
                  <button
                    className={styles.managementMinorButton}
                    onClick={() => onOpenKnowledgeBaseLibrary(knowledgeBase)}
                  >
                    打开
                  </button>
                  <button
                    className={styles.managementMinorButton}
                    disabled={writeDisabled || savingKnowledgeBase}
                    onClick={() => openEditKnowledgeBaseModal(knowledgeBase)}
                  >
                    编辑
                  </button>
                  <button
                    className={styles.managementDangerMinorButton}
                    disabled={writeDisabled || savingKnowledgeBase}
                    onClick={() =>
                      void onDeleteKnowledgeBase(knowledgeBase.knowledge_base_id)
                    }
                  >
                    删除
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

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
