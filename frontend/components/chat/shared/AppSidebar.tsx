import type { MouseEvent } from 'react'

import styles from '../../ChatInterface.module.css'
import type { ActorState } from '../../chat-interface/auth'
import { DEFAULT_KNOWLEDGE_PAGE } from '../../chat-interface/constants'
import type {
  ChannelManagementPage,
  ChatHistorySession,
  KnowledgePage,
  ViewMode,
} from '../../chat-interface/types'
import { formatDateTime } from '../../chat-interface/utils'
import { AccountPanel } from './AccountPanel'
import { SidebarIcon } from './BrandIcons'

interface AppSidebarProps {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
  viewMode: ViewMode
  knowledgePage: KnowledgePage
  channelPage: ChannelManagementPage
  onNavigate: (
    view: ViewMode,
    knowledgePage?: KnowledgePage,
    channelPage?: ChannelManagementPage
  ) => void
  historyExpanded: boolean
  onToggleHistory: () => void
  historyLoading: boolean
  historyError: string
  historySessions: ChatHistorySession[]
  sessionId: string
  historyLoadingSessionId: string | null
  runningThreadIds: string[]
  onOpenHistorySession: (sessionId: string) => void | Promise<void>
  onDeleteHistorySession: (
    sessionId: string,
    event: MouseEvent<HTMLButtonElement>
  ) => void | Promise<void>
  channelNavExpanded: boolean
  onChannelsNavClick: () => void
  actor: ActorState
  accountMenuOpen: boolean
  onAccountMenuOpenChange: (open: boolean) => void
  onLogout: () => void
}

/**
 * 渲染应用左侧导航、聊天历史和账号区域。
 *
 * Args:
 *   sidebarCollapsed: 侧边栏是否折叠。
 *   onToggleSidebar: 切换侧边栏折叠状态。
 *   viewMode: 当前页面。
 *   knowledgePage: 当前知识库子页面。
 *   channelPage: 当前渠道子页面。
 *   onNavigate: 页面导航回调。
 *   historyExpanded: 聊天历史是否展开。
 *   onToggleHistory: 切换聊天历史展开状态。
 *   historyLoading: 聊天历史是否加载中。
 *   historyError: 聊天历史错误。
 *   historySessions: 聊天历史列表。
 *   sessionId: 当前会话 ID。
 *   historyLoadingSessionId: 正在加载的历史会话 ID。
 *   runningThreadIds: 后台运行中的线程 ID。
 *   onOpenHistorySession: 打开历史会话。
 *   onDeleteHistorySession: 删除历史会话。
 *   channelNavExpanded: 渠道子菜单是否展开。
 *   onChannelsNavClick: 渠道导航点击回调。
 *   actor: 当前登录主体。
 *   accountMenuOpen: 账号菜单是否展开。
 *   onAccountMenuOpenChange: 账号菜单展开状态变更。
 *   onLogout: 退出登录。
 */
export function AppSidebar({
  sidebarCollapsed,
  onToggleSidebar,
  viewMode,
  knowledgePage,
  channelPage,
  onNavigate,
  historyExpanded,
  onToggleHistory,
  historyLoading,
  historyError,
  historySessions,
  sessionId,
  historyLoadingSessionId,
  runningThreadIds,
  onOpenHistorySession,
  onDeleteHistorySession,
  channelNavExpanded,
  onChannelsNavClick,
  actor,
  accountMenuOpen,
  onAccountMenuOpenChange,
  onLogout,
}: AppSidebarProps) {
  return (
    <aside
      className={`${styles.sidebarNav} ${
        sidebarCollapsed ? styles.sidebarNavCollapsed : ''
      }`}
    >
      <div className={styles.sidebarPanel}>
        <div className={styles.sidebarBrand}>
          <div className={styles.logoArea}>
            {sidebarCollapsed ? (
              <span className={styles.logoIcon}>
                <img
                  className={styles.logoMark}
                  src="/logo-mark.png"
                  alt=""
                  aria-hidden="true"
                />
              </span>
            ) : null}
            <div className={styles.sidebarBrandDetails}>
              <img
                className={styles.brandWordmark}
                src="/logo.png"
                alt="DeepClaw"
              />
              <p className={styles.subtitle}>Agent workspace</p>
            </div>
          </div>
          <button
            className={styles.sidebarCollapseButton}
            onClick={onToggleSidebar}
            aria-label={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
            title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? '›' : '‹'}
          </button>
        </div>
        <p className={styles.sidebarSectionLabel}>工作台</p>
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'chat' ? styles.sidebarButtonActive : ''
          }`}
          onClick={() => onNavigate('chat')}
        >
          <SidebarIcon name="chat" />
          <span className={styles.sidebarButtonLabel}>聊天</span>
        </button>
        {viewMode === 'chat' ? (
          <section className={styles.chatHistory} aria-label="聊天历史">
            <div className={styles.chatHistoryHeader}>
              <button
                type="button"
                className={styles.chatHistoryToggleButton}
                onClick={onToggleHistory}
                aria-expanded={historyExpanded}
              >
                <span className={styles.chatHistoryTitle}>聊天历史</span>
                <span aria-hidden="true">{historyExpanded ? '⌃' : '⌄'}</span>
              </button>
            </div>
            {historyExpanded && historyLoading ? (
              <div className={styles.chatHistoryStatus}>正在加载…</div>
            ) : null}
            {historyExpanded && historyError ? (
              <div className={styles.chatHistoryError}>{historyError}</div>
            ) : null}
            {historyExpanded &&
            !historyLoading &&
            !historyError &&
            historySessions.length === 0 ? (
              <div className={styles.chatHistoryStatus}>暂无历史会话</div>
            ) : null}
            {historyExpanded && historySessions.length > 0 ? (
              <div className={styles.chatHistoryList}>
                {historySessions.map((historySession) => {
                  const isActive = historySession.session_id === sessionId
                  const isLoading =
                    historyLoadingSessionId === historySession.session_id
                  const isRunning = runningThreadIds.includes(
                    historySession.session_id
                  )
                  return (
                    <div
                      key={historySession.session_id}
                      className={`${styles.chatHistoryItem} ${
                        isActive ? styles.chatHistoryItemActive : ''
                      }`}
                    >
                      <button
                        type="button"
                        className={styles.chatHistoryOpenButton}
                        onClick={() =>
                          void onOpenHistorySession(historySession.session_id)
                        }
                        disabled={isLoading}
                      >
                        <span className={styles.chatHistoryItemContent}>
                          <span className={styles.chatHistorySessionTitle}>
                            {historySession.title || '未命名对话'}
                          </span>
                          <span className={styles.chatHistoryTime}>
                            {isRunning
                              ? isActive
                                ? '运行中 · '
                                : '后台运行中 · '
                              : ''}
                            {historySession.updated_at
                              ? formatDateTime(historySession.updated_at)
                              : '时间未知'}
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        className={styles.chatHistoryDeleteButton}
                        onClick={(event) =>
                          void onDeleteHistorySession(
                            historySession.session_id,
                            event
                          )
                        }
                        disabled={isLoading || isRunning}
                        aria-label={`删除会话 ${historySession.session_id}`}
                      >
                        删除
                      </button>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </section>
        ) : null}
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'knowledge' && knowledgePage !== 'users'
              ? styles.sidebarButtonActive
              : ''
          }`}
          onClick={() => onNavigate('knowledge', 'libraries')}
        >
          <SidebarIcon name="knowledge" />
          <span className={styles.sidebarButtonLabel}>知识库</span>
        </button>
        <p className={styles.sidebarSectionLabel}>能力与连接</p>
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'skills' ? styles.sidebarButtonActive : ''
          }`}
          onClick={() => onNavigate('skills')}
        >
          <SidebarIcon name="skills" />
          <span className={styles.sidebarButtonLabel}>技能管理</span>
        </button>
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'mcp' ? styles.sidebarButtonActive : ''
          }`}
          onClick={() => onNavigate('mcp')}
        >
          <SidebarIcon name="mcp" />
          <span className={styles.sidebarButtonLabel}>MCP 管理</span>
        </button>
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'channels' ? styles.sidebarButtonActive : ''
          }`}
          onClick={onChannelsNavClick}
        >
          <SidebarIcon name="channels" />
          <span className={styles.sidebarButtonLabel}>渠道管理</span>
          <span
            className={
              channelNavExpanded
                ? styles.sidebarChevronExpanded
                : styles.sidebarChevron
            }
          >
            ▾
          </span>
        </button>
        {channelNavExpanded ? (
          <div className={styles.channelSubnav}>
            <button
              className={`${styles.channelSubnavItem} ${
                viewMode === 'channels' && channelPage === 'weixin'
                  ? styles.channelSubnavItemActive
                  : ''
              }`}
              onClick={() =>
                onNavigate('channels', DEFAULT_KNOWLEDGE_PAGE, 'weixin')
              }
            >
              <span className={styles.channelSubnavLabel}>微信绑定</span>
              <span className={styles.channelSubnavMeta}>扫码与状态</span>
            </button>
            <button
              className={`${styles.channelSubnavItem} ${
                viewMode === 'channels' && channelPage === 'feishu'
                  ? styles.channelSubnavItemActive
                  : ''
              }`}
              onClick={() =>
                onNavigate('channels', DEFAULT_KNOWLEDGE_PAGE, 'feishu')
              }
            >
              <span className={styles.channelSubnavLabel}>飞书绑定</span>
              <span className={styles.channelSubnavMeta}>配置与状态</span>
            </button>
          </div>
        ) : null}
        <button
          className={`${styles.sidebarButton} ${
            viewMode === 'knowledge' && knowledgePage === 'users'
              ? styles.sidebarButtonActive
              : ''
          }`}
          onClick={() => onNavigate('knowledge', 'users')}
        >
          <SidebarIcon name="users" />
          <span className={styles.sidebarButtonLabel}>用户管理</span>
        </button>
      </div>
      <div className={styles.sidebarAccount}>
        <AccountPanel
          actor={actor}
          open={accountMenuOpen}
          onOpenChange={onAccountMenuOpenChange}
          onLogout={onLogout}
        />
      </div>
    </aside>
  )
}
