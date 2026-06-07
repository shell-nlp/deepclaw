'use client'

import type { ChangeEvent, MouseEvent, Ref } from 'react'

import styles from '../ChatInterface.module.css'
import {
  MANAGEMENT_PAGE_DESCRIPTION_MAP,
  MANAGEMENT_PAGE_TITLE_MAP,
} from './constants'
import { CreateKnowledgeBaseModal } from './CreateKnowledgeBaseModal'
import { Pagination } from './Pagination'
import type {
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeDocumentDetailResponse,
  KnowledgePage,
  ViewMode,
} from './types'
import { formatDateTime } from './utils'

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
  selectedKnowledgeBaseName: string
  selectedKnowledgeBaseDescription: string
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
  onSelectedKnowledgeBaseNameChange: (value: string) => void
  onSelectedKnowledgeBaseDescriptionChange: (value: string) => void
  onSaveKnowledgeBase: () => void | Promise<void>
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
  selectedKnowledgeBaseName,
  selectedKnowledgeBaseDescription,
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
  onSelectedKnowledgeBaseNameChange,
  onSelectedKnowledgeBaseDescriptionChange,
  onSaveKnowledgeBase,
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
  const renderDocumentDetailPage = () =>
    selectedDocumentDetail ? (
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
            <p>{selectedKnowledgeBase.description || '当前知识库暂无描述。'}</p>
          </div>
          <div className={styles.managementHeroActions}>
            <button
              className={styles.managementMinorButton}
              onClick={() => onNavigateTo('knowledge', 'libraries')}
            >
              返回知识库列表
            </button>
            <button
              className={styles.managementDangerButton}
              disabled={writeDisabled}
              onClick={() => void onDeleteKnowledgeBase()}
            >
              删除知识库
            </button>
          </div>
        </section>

        <div className={styles.managementSummaryGrid}>
          <div className={styles.managementSummaryCard}>
            <span className={styles.managementSummaryLabel}>文档总数</span>
            <strong className={styles.managementSummaryValue}>
              {selectedKnowledgeBase.document_count}
            </strong>
            <span className={styles.managementMeta}>当前知识库文档数量</span>
          </div>
          <div className={styles.managementSummaryCard}>
            <span className={styles.managementSummaryLabel}>切片总数</span>
            <strong className={styles.managementSummaryValue}>
              {selectedKnowledgeBase.chunk_count}
            </strong>
            <span className={styles.managementMeta}>切片会进入检索索引</span>
          </div>
          <div className={styles.managementSummaryCard}>
            <span className={styles.managementSummaryLabel}>图前缀</span>
            <strong className={styles.managementSummaryValue}>
              {selectedKnowledgeBase.index_prefix}
            </strong>
            <span className={styles.managementMeta}>当前图检索命名空间</span>
          </div>
          <div className={styles.managementSummaryCard}>
            <span className={styles.managementSummaryLabel}>更新时间</span>
            <strong className={styles.managementSummaryValue}>
              {formatDateTime(selectedKnowledgeBase.updated_at)}
            </strong>
            <span className={styles.managementMeta}>最近一次知识库变更时间</span>
          </div>
        </div>

        <div className={styles.managementPageGrid}>
          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>知识库设置</h3>
              <span className={styles.managementMeta}>名称与描述</span>
            </div>
            <div className={styles.managementForm}>
              <input
                className={styles.managementInput}
                value={selectedKnowledgeBaseName}
                disabled={writeDisabled}
                onChange={(event) =>
                  onSelectedKnowledgeBaseNameChange(event.target.value)
                }
                placeholder="知识库名称"
              />
              <input
                className={styles.managementInput}
                value={selectedKnowledgeBaseDescription}
                disabled={writeDisabled}
                onChange={(event) =>
                  onSelectedKnowledgeBaseDescriptionChange(event.target.value)
                }
                placeholder="知识库描述"
              />
              <div className={styles.managementToolbar}>
                <button
                  className={styles.managementButton}
                  disabled={savingKnowledgeBase || writeDisabled}
                  onClick={() => void onSaveKnowledgeBase()}
                >
                  保存设置
                </button>
              </div>
            </div>

            <div className={styles.managementDivider} />

            <div className={styles.managementHeader}>
              <h3>添加知识</h3>
              <span className={styles.managementMeta}>支持 PDF / DOCX 等文件</span>
            </div>
            <div className={styles.managementToolbar}>
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

            <div className={styles.managementMetaPanel}>
              <span>Passage: {selectedKnowledgeBase.passage_index}</span>
              <span>Entity: {selectedKnowledgeBase.entity_index}</span>
              <span>Relation: {selectedKnowledgeBase.relation_index}</span>
            </div>
          </section>

          <section className={styles.managementCard}>
            <div className={styles.managementHeader}>
              <h3>知识列表</h3>
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
                <div className={styles.managementEmpty}>当前知识库还没有知识文档。</div>
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
            <Pagination
              page={documentPage}
              pageTotal={documentPageTotal}
              total={documentTotal}
              onPrev={() => onDocumentPageChange((prev) => Math.max(1, prev - 1))}
              onNext={() =>
                onDocumentPageChange((prev) => Math.min(documentPageTotal, prev + 1))
              }
            />
          </section>
        </div>
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
          <h2>按知识库管理你的知识</h2>
          <p>
            这里展示当前账号下的所有知识库。点开卡片可继续上传知识文档，并查看检索切片详情。
          </p>
        </div>
      </section>

      <div className={styles.managementSummaryGrid}>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>知识库数量</span>
          <strong className={styles.managementSummaryValue}>{knowledgeBaseTotal}</strong>
          <span className={styles.managementMeta}>当前可见的知识库总数</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>切片总量</span>
          <strong className={styles.managementSummaryValue}>{visibleChunkTotal}</strong>
          <span className={styles.managementMeta}>当前页知识库切片汇总</span>
        </div>
      </div>

      <div className={styles.managementToolbar}>
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
        <button
          className={styles.managementDangerButton}
          disabled={checkedKnowledgeBaseIds.length === 0 || deletingBulk || writeDisabled}
          onClick={() => void onBulkDeleteKnowledgeBases()}
        >
          批量删除
        </button>
      </div>

      <div className={styles.managementLibraryGrid}>
        <button
          type="button"
          className={styles.managementCreateCard}
          disabled={writeDisabled}
          onClick={() => onShowCreateKnowledgeBaseModalChange(true)}
        >
          <span className={styles.managementCreateIcon}>+</span>
          <strong>新建知识库</strong>
          <span>点击后填写知识库名称和描述</span>
        </button>

        {knowledgeBases.length === 0 ? (
          <div className={styles.managementEmpty}>暂无知识库。</div>
        ) : (
          knowledgeBases.map((knowledgeBase) => (
            <div
              key={knowledgeBase.knowledge_base_id}
              className={`${styles.managementLibraryCard} ${
                selectedKnowledgeBaseId === knowledgeBase.knowledge_base_id
                  ? styles.managementListItemActive
                  : ''
              }`}
            >
              <div className={styles.managementListHeader}>
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
                    checked={checkedKnowledgeBaseIds.includes(
                      knowledgeBase.knowledge_base_id
                    )}
                    onChange={() => undefined}
                  />
                </label>
                <strong>{knowledgeBase.name}</strong>
                <span>{knowledgeBase.document_count} 文档</span>
              </div>
              <p className={styles.managementDescription}>
                {knowledgeBase.description || '暂无描述'}
              </p>
              <div className={styles.managementListMeta}>
                <span>{knowledgeBase.chunk_count} 切片</span>
                <span>{formatDateTime(knowledgeBase.updated_at)}</span>
              </div>
              <div className={styles.managementActionRow}>
                <button
                  className={styles.managementButton}
                  onClick={() => onOpenKnowledgeBaseLibrary(knowledgeBase)}
                >
                  进入知识库
                </button>
                <button
                  className={styles.managementDangerMinorButton}
                  disabled={writeDisabled}
                  onClick={() => void onDeleteKnowledgeBase(knowledgeBase.knowledge_base_id)}
                >
                  删除
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <Pagination
        page={knowledgeBasePage}
        pageTotal={knowledgeBasePageTotal}
        total={knowledgeBaseTotal}
        onPrev={() => onKnowledgeBasePageChange((prev) => Math.max(1, prev - 1))}
        onNext={() =>
          onKnowledgeBasePageChange((prev) => Math.min(knowledgeBasePageTotal, prev + 1))
        }
      />
    </div>
  )

  const renderKnowledgePage = () => {
    if (knowledgePage === 'document-detail') return renderDocumentDetailPage()
    if (knowledgePage === 'library-detail') return renderLibraryDetailPage()
    return renderLibrariesPage()
  }

  return (
    <>
      <div className={styles.managementPage}>
        <div className={styles.managementNoticeRow}>
          {writeDisabled ? (
            <div className={styles.managementNotice}>{writeDisabledMessage}</div>
          ) : null}
          {managementNotice ? (
            <div className={styles.managementNotice}>{managementNotice}</div>
          ) : null}
          {managementError ? <div className={styles.managementError}>{managementError}</div> : null}
        </div>
        <div className={styles.managementTopbar}>
          <div className={styles.managementRouteInfo}>
            <span className={styles.managementBreadcrumb}>
              知识管理 / {MANAGEMENT_PAGE_TITLE_MAP[knowledgePage]}
            </span>
            <h2>{MANAGEMENT_PAGE_TITLE_MAP[knowledgePage]}</h2>
            <p>{MANAGEMENT_PAGE_DESCRIPTION_MAP[knowledgePage]}</p>
          </div>
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
    </>
  )
}
