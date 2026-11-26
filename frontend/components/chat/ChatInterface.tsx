'use client'

import styles from '../ChatInterface.module.css'
import { ChatView } from './ChatView'
import { ScheduleManagementView } from './management/ScheduleManagementView'
import scheduleStyles from './management/Schedules.module.css'
import { ScheduleBell } from './shared/ScheduleBell'
import { AppSidebar } from './shared/AppSidebar'
import { ChannelManagementView } from './management/ChannelManagementView'
import { KnowledgeManagementView } from './management/KnowledgeManagementView'
import { FileKnowledgeView } from './management/FileKnowledgeView'
import { getRouteHash } from './utils'
import { McpManagementView } from './management/McpManagementView'
import { SkillManagementView } from './management/SkillManagementView'
import { RbacManagementView } from './management/RbacManagementView'
import { UserManagementView } from './management/UserManagementView'
import { useChatPageController } from './hooks/useChatPageController'
import { useRoleCatalog } from './hooks/useRoleCatalog'
import { DeviceManagementView } from './management/DeviceManagementView'
import { ModelManagementView } from './management/ModelManagementView'

export default function ChatInterface() {
  const {
    deviceState,
    viewMode,
    channelPage,
    channelNavExpanded,
    systemNavExpanded,
    sidebarCollapsed,
    knowledgePage,
    messages,
    inputValue,
    setInputValue,
    draftImages,
    draftFiles,
    setDraftFiles,
    setDraftImages,
    chatModels,
    selectedModelId,
    setSelectedModelId,
    reasoningChoice,
    setReasoningChoice,
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
    withAuthHeaders,
    handleRetryMessage,
    navigateTo,
    openHistorySession,
    deleteHistorySession,
    handleChannelsNavClick,
    handleSystemNavClick,
    toggleSidebar,
    navigateToKnowledgeView,
    loadAdminUsers,
    handleKnowledgePickerOpenChange,
    handleKnowledgeSelectionChange,
    chatModeOptions,
    activeChatModeId,
    handleChatModeChange,
    saveMcpConfig,
    saveMcpServer,
    formatMcpConfig,
    toggleMcpEnabled,
    toggleMcpServer,
    loadMcpExample,
    clearMcpConfig,
    handleLogout,
    openLoginPage,
    createAdminUser,
    updateAdminUserRole,
    updateAdminUserStatus,
    updateAdminUserProfile,
    deleteAdminUser,
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

  const roleCatalog = useRoleCatalog(requestJson, actorCapabilities.canManageRoles)
  const scheduleBell = actorCapabilities.canViewSchedules && (
    <ScheduleBell key={actor.userId} requestJson={requestJson} withAuthHeaders={withAuthHeaders}
      canManage={actorCapabilities.canManageSchedules} />
  )
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
          canViewChat={actorCapabilities.canViewChat}
          canUseChat={actorCapabilities.canUseChat}
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
          systemNavExpanded={systemNavExpanded}
          onSystemNavClick={handleSystemNavClick}
          actor={actor}
          canManageUsers={actorCapabilities.canManageUsers}
          canManageRoles={actorCapabilities.canManageRoles}
          accountMenuOpen={accountMenuOpen}
          onAccountMenuOpenChange={setAccountMenuOpen}
          onLogout={handleLogout}
        />

        <main className={styles.mainContent}>
          {viewMode !== 'chat' && scheduleBell && <div className={scheduleStyles.toolbar}>{scheduleBell}</div>}
          {viewMode === 'knowledge' && knowledgePage !== 'users' && knowledgePage !== 'roles' && (
            <nav className={styles.knowledgeNavigation} aria-label="知识库类型">
              <a href={getRouteHash('knowledge', 'libraries')} aria-current={knowledgePage !== 'files' ? 'true' : undefined}>
                知识库
              </a>
              <a href={getRouteHash('knowledge', 'files')} aria-current={knowledgePage === 'files' ? 'true' : undefined}>
                文件知识库
              </a>
            </nav>
          )}
          {viewMode === 'chat' ? (
            <ChatView
              notifications={scheduleBell}
              devices={deviceState.available}
              selectedDeviceId={deviceState.selectedDeviceId}
              onDeviceChange={deviceState.setSelectedDeviceId}
              messages={messages}
              sessionId={sessionId}
              chatModeOptions={chatModeOptions}
              activeChatModeId={activeChatModeId}
              mcpStatusLabel={actorCapabilities.canUseMcp ? mcpStatusLabel : 'MCP 未授权'}
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
              draftImages={draftImages}
              onDraftImagesChange={setDraftImages}
              draftFiles={draftFiles}
              onDraftFilesChange={setDraftFiles}
              fileDraftKey={`${actor.userId}/${sessionId}`}
              canAttachFiles={actorCapabilities.canReadChatFiles && actorCapabilities.canWriteChatFiles}
              canReadFiles={actorCapabilities.canReadChatFiles}
              requestJson={requestJson}
              withAuthHeaders={withAuthHeaders}
              chatModels={chatModels}
              selectedModelId={selectedModelId}
              onModelChange={setSelectedModelId}
              reasoningChoice={reasoningChoice}
              onReasoningChoiceChange={setReasoningChoice}
              chatDisabled={chatDisabled}
              canUseChat={actorCapabilities.canUseChat}
              internetSearch={internetSearch}
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
              onNavigateToKnowledge={() => navigateTo('knowledge', 'libraries')}
              onNavigateToFiles={() => navigateTo('knowledge', 'files')}
              onAbortRequest={abortRequest}
              onSendMessage={sendMessage}
              onRecommendedQuestion={askRecommendedQuestion}
              onRetryMessage={handleRetryMessage}
            />
          ) : viewMode === 'schedules' ? (
            <div className={styles.managementViewport}>
              <ScheduleManagementView key={actor.userId} requestJson={requestJson} isGuest={actor.isGuest}
                canView={actorCapabilities.canViewSchedules} canManage={actorCapabilities.canManageSchedules}
                onLogin={openLoginPage} />
            </div>
          ) : viewMode === 'devices' ? (
            <div className={styles.managementViewport}>
              <DeviceManagementView key={actor.userId} actor={actor} state={deviceState} requestJson={requestJson} onLogin={openLoginPage}/>
            </div>
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
              {actorCapabilities.canUseMcp ? <McpManagementView
                mcpEnabled={mcpEnabled}
                mcpConfigDraft={mcpConfigDraft}
                mcpConfigDirty={mcpConfigDirty}
                mcpNotice={mcpNotice}
                mcpError={mcpError}
                draftError={mcpDraftParseResult.error}
                savedServerCount={savedMcpParseResult.serverSummaries.length}
                savedServerSummaries={savedMcpParseResult.serverSummaries}
                savedConfig={savedMcpParseResult.config}
                requestJson={requestJson}
                onMcpConfigDraftChange={setMcpConfigDraft}
                onSaveMcpConfig={saveMcpConfig}
                onSaveMcpServer={saveMcpServer}
                onFormatMcpConfig={formatMcpConfig}
                onToggleMcpEnabled={toggleMcpEnabled}
                onToggleMcpServer={toggleMcpServer}
                onLoadMcpExample={loadMcpExample}
                onClearMcpConfig={clearMcpConfig}
              /> : <p>当前账号没有使用 MCP 的权限。</p>}
            </div>
          ) : viewMode === 'models' ? (
            <div className={styles.managementViewport}>
              <ModelManagementView actor={actor} requestJson={requestJson} canManage={actorCapabilities.canManageModels} />
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
          ) : knowledgePage === 'files' ? (
            <div className={styles.managementViewport}>
              <FileKnowledgeView key={actor.userId} isGuest={actor.isGuest}
                canRead={actorCapabilities.canReadChatFiles}
                canWrite={actorCapabilities.canWriteChatFiles}
                requestJson={requestJson} withAuthHeaders={withAuthHeaders} />
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
                requestJson={requestJson}
                canManageUsers={actorCapabilities.canManageUsers}
                onCreateUser={createAdminUser}
                onUpdateUserRole={updateAdminUserRole}
                onUpdateUserStatus={updateAdminUserStatus}
                onUpdateUserProfile={updateAdminUserProfile}
                onDeleteUser={deleteAdminUser}
                currentUserId={currentUserId}
                onResetUserPassword={resetAdminUserPassword}
              />
            </div>
          ) : knowledgePage === 'roles' ? (
            <div className={styles.managementViewport}>
              <RbacManagementView
                canView={actorCapabilities.canViewRoles}
                canManage={actorCapabilities.canManageRoles}
                catalog={roleCatalog.roles}
                permissionDefinitions={roleCatalog.permissions}
                loading={roleCatalog.loading}
                busy={roleCatalog.busy}
                notice={roleCatalog.notice}
                error={roleCatalog.error}
                onCreateRole={roleCatalog.createRole}
                onSaveRole={roleCatalog.saveRole}
                onDeleteRole={roleCatalog.deleteRole}
                onSavePermissions={roleCatalog.savePermissions}
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
