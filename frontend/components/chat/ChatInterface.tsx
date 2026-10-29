'use client'

import styles from '../ChatInterface.module.css'
import { ChatView } from './ChatView'
import { AppSidebar } from './shared/AppSidebar'
import { ChannelManagementView } from './management/ChannelManagementView'
import { KnowledgeManagementView } from './management/KnowledgeManagementView'
import { McpManagementView } from './management/McpManagementView'
import { SkillManagementView } from './management/SkillManagementView'
import { UserManagementView } from './management/UserManagementView'
import { useChatPageController } from './hooks/useChatPageController'

export default function ChatInterface() {
  const {
    viewMode,
    channelPage,
    channelNavExpanded,
    sidebarCollapsed,
    knowledgePage,
    messages,
    inputValue,
    setInputValue,
    sessionId,
    historySessions,
    historyExpanded,
    setHistoryExpanded,
    historyLoading,
    historyLoadingSessionId,
    historyError,
    status,
    isProcessing,
    runningThreadIds,
    internetSearch,
    setInternetSearch,
    deepThinking,
    setDeepThinking,
    isKnowledgeMode,
    selectedKnowledgeBaseIds,
    knowledgeBaseOptions,
    knowledgePickerOpen,
    loadingKnowledgeBaseOptions,
    showInterrupt,
    interruptData,
    toolCallDurations,
    actor,
    accountMenuOpen,
    setAccountMenuOpen,
    adminUsers,
    loadingAdminUsers,
    userAdminNotice,
    userAdminError,
    knowledgeBases,
    knowledgeBaseTotal,
    knowledgeBasePage,
    setKnowledgeBasePage,
    knowledgeBaseSearchInput,
    setKnowledgeBaseSearchInput,
    setKnowledgeBaseSearch,
    selectedKnowledgeBaseId,
    selectedKnowledgeBase,
    checkedKnowledgeBaseIds,
    documents,
    uploadTasks,
    documentTotal,
    documentPage,
    setDocumentPage,
    documentSearchInput,
    setDocumentSearchInput,
    setDocumentSearch,
    checkedDocumentIds,
    selectedDocumentDetail,
    documentChunkPage,
    setDocumentChunkPage,
    loadingDocumentDetail,
    knowledgeBaseName,
    setKnowledgeBaseName,
    knowledgeBaseDescription,
    setKnowledgeBaseDescription,
    showCreateKnowledgeBaseModal,
    setShowCreateKnowledgeBaseModal,
    mcpConfigDraft,
    setMcpConfigDraft,
    mcpEnabled,
    mcpNotice,
    mcpError,
    skills,
    loadingSkills,
    uploadingSkills,
    skillNotice,
    skillError,
    managementError,
    managementNotice,
    loadingDocuments,
    savingKnowledgeBase,
    uploadingDocuments,
    deletingBulk,
    chatContainerRef,
    textareaRef,
    uploadInputRef,
    skillUploadInputRef,
    currentAssistantMessageIdRef,
    actorCapabilities,
    currentUserId,
    mcpDraftParseResult,
    savedMcpParseResult,
    mcpConfigDirty,
    handleChatScroll,
    clearChat,
    requestJson,
    handleRetryMessage,
    navigateTo,
    openHistorySession,
    deleteHistorySession,
    handleChannelsNavClick,
    toggleSidebar,
    navigateToKnowledgeView,
    loadAdminUsers,
    handleKnowledgePickerOpenChange,
    handleKnowledgeSelectionChange,
    chatModeOptions,
    activeChatModeId,
    handleChatModeChange,
    saveMcpConfig,
    formatMcpConfig,
    toggleMcpEnabled,
    loadMcpExample,
    clearMcpConfig,
    handleLogout,
    openLoginPage,
    createAdminUser,
    updateAdminUserRole,
    updateAdminUserStatus,
    resetAdminUserPassword,
    openSkillUploadDialog,
    handleUploadSkill,
    deleteSkill,
    openKnowledgeBaseLibrary,
    openDocumentDetail,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    bulkDeleteKnowledgeBases,
    openUploadDialog,
    handleUploadFiles,
    retryUploadTask,
    deleteUploadTask,
    updateDocumentChunk,
    renameDocument,
    deleteDocument,
    bulkDeleteDocuments,
    sendMessage,
    handleKeyDown,
    askRecommendedQuestion,
    abortRequest,
    handleInterruptAction,
    handleAskUserResponse,
    toggleKnowledgeBaseChecked,
    toggleDocumentChecked,
    knowledgeBasePageTotal,
    documentPageTotal,
    documentChunkPageTotal,
    visibleChunkTotal,
    chatDisabled,
    mcpStatusLabel,
  } = useChatPageController()

  return (
    <div className={styles.container}>
      <div className={styles.backgroundGrid} />
      <div className={styles.backgroundGlow} />

      <div
        className={`${styles.workspaceLayout} ${
          sidebarCollapsed ? styles.workspaceLayoutSidebarCollapsed : ''
        }`}
      >
        <AppSidebar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          viewMode={viewMode}
          knowledgePage={knowledgePage}
          channelPage={channelPage}
          onNavigate={navigateTo}
          historyExpanded={historyExpanded}
          onToggleHistory={() => setHistoryExpanded((expanded) => !expanded)}
          historyLoading={historyLoading}
          historyError={historyError}
          historySessions={historySessions}
          sessionId={sessionId}
          historyLoadingSessionId={historyLoadingSessionId}
          runningThreadIds={runningThreadIds}
          onOpenHistorySession={openHistorySession}
          onDeleteHistorySession={deleteHistorySession}
          channelNavExpanded={channelNavExpanded}
          onChannelsNavClick={handleChannelsNavClick}
          actor={actor}
          accountMenuOpen={accountMenuOpen}
          onAccountMenuOpenChange={setAccountMenuOpen}
          onLogout={handleLogout}
        />

        <main className={styles.mainContent}>
          {viewMode === 'chat' ? (
            <ChatView
              messages={messages}
              sessionId={sessionId}
              chatModeOptions={chatModeOptions}
              activeChatModeId={activeChatModeId}
              mcpStatusLabel={mcpStatusLabel}
              status={status}
              isProcessing={isProcessing}
              isKnowledgeMode={isKnowledgeMode}
              knowledgeBaseOptions={knowledgeBaseOptions}
              selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
              knowledgePickerOpen={knowledgePickerOpen}
              loadingKnowledgeBaseOptions={loadingKnowledgeBaseOptions}
              showInterrupt={showInterrupt}
              interruptData={interruptData}
              inputValue={inputValue}
              chatDisabled={chatDisabled}
              internetSearch={internetSearch}
              deepThinking={deepThinking}
              currentAssistantMessageId={currentAssistantMessageIdRef.current}
              chatContainerRef={chatContainerRef}
              onChatScroll={handleChatScroll}
              textareaRef={textareaRef}
              toolCallDurations={toolCallDurations}
              onClearChat={clearChat}
              onInterruptAction={handleInterruptAction}
              onAskUserResponse={handleAskUserResponse}
              onInputChange={setInputValue}
              onKeyDown={handleKeyDown}
              onKnowledgePickerOpenChange={handleKnowledgePickerOpenChange}
              onKnowledgeSelectionChange={handleKnowledgeSelectionChange}
              onChatModeChange={handleChatModeChange}
              onInternetSearchChange={setInternetSearch}
              onDeepThinkingChange={setDeepThinking}
              onNavigateToKnowledge={() => navigateTo('knowledge', 'libraries')}
              onAbortRequest={abortRequest}
              onSendMessage={sendMessage}
              onRecommendedQuestion={askRecommendedQuestion}
              onRetryMessage={handleRetryMessage}
            />
          ) : viewMode === 'skills' ? (
            <div className={styles.managementViewport}>
              <SkillManagementView
                skills={skills}
                total={skills.length}
                uploadingSkills={uploadingSkills}
                loadingSkills={loadingSkills}
                skillNotice={skillNotice}
                skillError={skillError}
                canManageSkills={actorCapabilities.canManageSkills}
                disabledMessage=""
                uploadInputRef={skillUploadInputRef}
                onOpenUploadDialog={openSkillUploadDialog}
                onUploadSkills={handleUploadSkill}
                onDeleteSkill={deleteSkill}
              />
            </div>
          ) : viewMode === 'mcp' ? (
            <div className={styles.managementViewport}>
              <McpManagementView
                mcpEnabled={mcpEnabled}
                mcpConfigDraft={mcpConfigDraft}
                mcpConfigDirty={mcpConfigDirty}
                mcpNotice={mcpNotice}
                mcpError={mcpError}
                draftError={mcpDraftParseResult.error}
                savedServerCount={savedMcpParseResult.serverSummaries.length}
                draftServerSummaries={mcpDraftParseResult.serverSummaries}
                onMcpConfigDraftChange={setMcpConfigDraft}
                onSaveMcpConfig={saveMcpConfig}
                onFormatMcpConfig={formatMcpConfig}
                onToggleMcpEnabled={toggleMcpEnabled}
                onLoadMcpExample={loadMcpExample}
                onClearMcpConfig={clearMcpConfig}
              />
            </div>
          ) : viewMode === 'channels' ? (
            <div className={styles.managementViewport}>
              <ChannelManagementView
                actor={actor}
                userId={currentUserId}
                channelPage={channelPage}
                requestJson={requestJson}
              />
            </div>
          ) : knowledgePage === 'users' ? (
            <div className={styles.managementViewport}>
              <UserManagementView
                actor={actor}
                users={adminUsers}
                loading={loadingAdminUsers}
                notice={userAdminNotice}
                error={userAdminError}
                onOpenAuth={openLoginPage}
                onLoadUsers={loadAdminUsers}
                onCreateUser={createAdminUser}
                onUpdateUserRole={updateAdminUserRole}
                onUpdateUserStatus={updateAdminUserStatus}
                onResetUserPassword={resetAdminUserPassword}
              />
            </div>
          ) : (
            <div className={styles.managementViewport}>
              <KnowledgeManagementView
                knowledgePage={knowledgePage}
                managementNotice={managementNotice}
                managementError={managementError}
                writeDisabled={!actorCapabilities.canManageKnowledge}
                writeDisabledMessage=""
                knowledgeBaseTotal={knowledgeBaseTotal}
                visibleChunkTotal={visibleChunkTotal}
                knowledgeBases={knowledgeBases}
                selectedKnowledgeBaseId={selectedKnowledgeBaseId}
                selectedKnowledgeBase={selectedKnowledgeBase}
                checkedKnowledgeBaseIds={checkedKnowledgeBaseIds}
                knowledgeBaseSearchInput={knowledgeBaseSearchInput}
                knowledgeBasePage={knowledgeBasePage}
                knowledgeBasePageTotal={knowledgeBasePageTotal}
                documents={documents}
                uploadTasks={uploadTasks}
                documentTotal={documentTotal}
                documentPage={documentPage}
                documentPageTotal={documentPageTotal}
                documentSearchInput={documentSearchInput}
                checkedDocumentIds={checkedDocumentIds}
                selectedDocumentDetail={selectedDocumentDetail}
                documentChunkPage={documentChunkPage}
                documentChunkPageTotal={documentChunkPageTotal}
                knowledgeBaseName={knowledgeBaseName}
                knowledgeBaseDescription={knowledgeBaseDescription}
                showCreateKnowledgeBaseModal={showCreateKnowledgeBaseModal}
                savingKnowledgeBase={savingKnowledgeBase}
                uploadingDocuments={uploadingDocuments}
                deletingBulk={deletingBulk}
                loadingDocuments={loadingDocuments}
                loadingDocumentDetail={loadingDocumentDetail}
                uploadInputRef={uploadInputRef}
                onNavigateTo={navigateToKnowledgeView}
                onUpdateKnowledgeBase={updateKnowledgeBase}
                onDeleteKnowledgeBase={deleteKnowledgeBase}
                onOpenUploadDialog={openUploadDialog}
                onHandleUploadFiles={handleUploadFiles}
                onRetryUploadTask={retryUploadTask}
                onDeleteUploadTask={deleteUploadTask}
                onUpdateDocumentChunk={updateDocumentChunk}
                onDocumentSearchInputChange={setDocumentSearchInput}
                onDocumentPageChange={setDocumentPage}
                onDocumentSearchChange={setDocumentSearch}
                onBulkDeleteDocuments={bulkDeleteDocuments}
                onToggleDocumentChecked={toggleDocumentChecked}
                onOpenDocumentDetail={openDocumentDetail}
                onRenameDocument={renameDocument}
                onDeleteDocument={deleteDocument}
                onDocumentChunkPageChange={setDocumentChunkPage}
                onKnowledgeBaseSearchInputChange={setKnowledgeBaseSearchInput}
                onKnowledgeBasePageChange={setKnowledgeBasePage}
                onKnowledgeBaseSearchChange={setKnowledgeBaseSearch}
                onBulkDeleteKnowledgeBases={bulkDeleteKnowledgeBases}
                onShowCreateKnowledgeBaseModalChange={setShowCreateKnowledgeBaseModal}
                onToggleKnowledgeBaseChecked={toggleKnowledgeBaseChecked}
                onOpenKnowledgeBaseLibrary={openKnowledgeBaseLibrary}
                onKnowledgeBaseNameChange={setKnowledgeBaseName}
                onKnowledgeBaseDescriptionChange={setKnowledgeBaseDescription}
                onCreateKnowledgeBase={createKnowledgeBase}
              />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
