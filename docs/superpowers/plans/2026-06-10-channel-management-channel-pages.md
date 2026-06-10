# 渠道管理独立渠道页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前“渠道管理”从微信与飞书混排单页改造成“左侧可展开二级导航 + 微信/飞书独立工作台”，并保持现有绑定加载、创建、二维码与删除能力可用。

**Architecture:** 前端继续保留 `viewMode = 'channels'` 作为一级模块入口，在 `types.ts` 和 `utils.ts` 中增加渠道子页路由状态，在 `ChatInterface.tsx` 里接管侧栏展开、高亮和 hash 同步，在 `ChannelManagementView.tsx` 中只渲染当前渠道页。共享的绑定分组、摘要、筛选和二级导航辅助逻辑继续收口到 `channelManagement.ts`，用轻量 `node:test` 守住纯函数和路由行为，再通过 `pnpm lint` 与 `pnpm build` 做最终验证。

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS Modules, node:test

**Note:** 仓库 `AGENTS.md` 明确要求“未经用户明确要求，不要执行 `git add` / `git commit`”。因此本计划使用“差异复核”替代提交步骤；代码修改完成后还需要执行 `codegraph index --force` 更新索引。

---

### Task 1: 先建立渠道子页路由状态与纯函数测试基座

**Files:**
- Modify: `frontend/components/chat-interface/types.ts`
- Modify: `frontend/components/chat-interface/constants.ts`
- Modify: `frontend/components/chat-interface/utils.ts`
- Modify: `frontend/components/chat-interface/channelManagement.ts`
- Modify: `frontend/tests/channel-management.test.mjs`
- Create: `frontend/tests/channel-routing.test.mjs`

- [ ] **Step 1: 先写失败测试，固定渠道子页路由与默认页行为**

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import * as utilsPkg from '../components/chat-interface/utils.ts'
import * as channelManagementPkg from '../components/chat-interface/channelManagement.ts'

test('channel routes include the selected channel page in hash', () => {
  assert.equal(utilsPkg.getRouteHash('channels', 'libraries', 'weixin'), '#/channels/weixin')
  assert.equal(utilsPkg.getRouteHash('channels', 'libraries', 'feishu'), '#/channels/feishu')
})

test('channel routes parse unknown channel page back to weixin', () => {
  assert.deepEqual(utilsPkg.parseRouteHash('#/channels/unknown'), {
    viewMode: 'channels',
    knowledgePage: 'libraries',
    channelPage: 'weixin',
  })
})

test('channel management normalizes child page and remembers latest item', () => {
  assert.equal(channelManagementPkg.normalizeChannelManagementPage('feishu'), 'feishu')
  assert.equal(channelManagementPkg.normalizeChannelManagementPage('unknown'), 'weixin')
  assert.equal(
    channelManagementPkg.resolveChannelEntryPage('feishu', 'weixin'),
    'feishu'
  )
  assert.equal(
    channelManagementPkg.resolveChannelEntryPage(undefined, 'weixin'),
    'weixin'
  )
})
```

- [ ] **Step 2: 运行测试，确认当前实现还不认识 `channelPage`**

Run: `cd frontend && node --test tests/channel-routing.test.mjs tests/channel-management.test.mjs`

Expected: FAIL，报错会集中在：
- `getRouteHash()` 参数数量与返回值不匹配
- `parseRouteHash()` 没有 `channelPage`
- `normalizeChannelManagementPage()`、`resolveChannelEntryPage()` 尚不存在

- [ ] **Step 3: 最小实现渠道子页类型、默认值和 hash 解析**

```typescript
export type ChannelManagementPage = 'weixin' | 'feishu'

export const DEFAULT_CHANNEL_PAGE: ChannelManagementPage = 'weixin'

export function normalizeChannelManagementPage(
  value?: string
): ChannelManagementPage {
  return value === 'feishu' ? 'feishu' : 'weixin'
}

export function resolveChannelEntryPage(
  requestedPage?: string,
  lastVisitedPage: ChannelManagementPage = DEFAULT_CHANNEL_PAGE
): ChannelManagementPage {
  if (requestedPage) return normalizeChannelManagementPage(requestedPage)
  return normalizeChannelManagementPage(lastVisitedPage)
}

export function getRouteHash(
  viewMode: ViewMode,
  knowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE,
  channelPage: ChannelManagementPage = DEFAULT_CHANNEL_PAGE
): string {
  if (viewMode === 'channels') return `#/channels/${channelPage}`
  if (viewMode === 'chat') return '#/chat'
  if (viewMode === 'mcp') return '#/mcp'
  if (viewMode === 'skills') return '#/skills'
  return `#/knowledge/${knowledgePage}`
}

export function parseRouteHash(hash: string): {
  viewMode: ViewMode
  knowledgePage: KnowledgePage
  channelPage: ChannelManagementPage
} {
  const normalized = hash.replace(/^#/, '').replace(/^\/+/, '')
  const parts = normalized.split('/').filter(Boolean)

  if (parts[0] === 'mcp') {
    return {
      viewMode: 'mcp',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
      channelPage: DEFAULT_CHANNEL_PAGE,
    }
  }
  if (parts[0] === 'channels') {
    return {
      viewMode: 'channels',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
      channelPage: normalizeChannelManagementPage(parts[1]),
    }
  }
  if (parts[0] === 'skills') {
    return {
      viewMode: 'skills',
      knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
      channelPage: DEFAULT_CHANNEL_PAGE,
    }
  }
  if (parts[0] === 'knowledge') {
    return {
      viewMode: 'knowledge',
      knowledgePage: normalizeKnowledgePage(parts[1]),
      channelPage: DEFAULT_CHANNEL_PAGE,
    }
  }
  return {
    viewMode: 'chat',
    knowledgePage: DEFAULT_KNOWLEDGE_PAGE,
    channelPage: DEFAULT_CHANNEL_PAGE,
  }
}
```

- [ ] **Step 4: 重跑路由与工具测试，确认子页状态可以被稳定解析**

Run: `cd frontend && node --test tests/channel-routing.test.mjs tests/channel-management.test.mjs`

Expected: PASS，既有二维码与筛选测试继续通过，新路由测试通过。

- [ ] **Step 5: 复核差异，确认没有残留旧的 `#/channels` 裸路径假设**

Run: `rg -n "'#/channels'|\"#/channels\"|viewMode === 'channels' return '#/channels'" frontend/components frontend/tests`

Expected: 旧的裸路径拼接应改成统一的 `#/channels/<channelPage>`，仅解析兼容逻辑可保留必要兜底。

### Task 2: 改造 ChatInterface 左侧导航，接入可展开的渠道二级菜单

**Files:**
- Modify: `frontend/components/ChatInterface.tsx`
- Modify: `frontend/components/ChatInterface.module.css`
- Modify: `frontend/tests/branding.test.mjs`

- [ ] **Step 1: 先写失败测试，锁定渠道导航已经变成可展开二级结构**

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const frontendRoot = resolve(import.meta.dirname, '..')

function readFrontendFile(relativePath) {
  return readFileSync(resolve(frontendRoot, relativePath), 'utf8')
}

test('chat interface renders expandable channel navigation with child items', () => {
  const chatInterfaceSource = readFrontendFile('components/ChatInterface.tsx')

  assert.match(chatInterfaceSource, /channelNavExpanded/)
  assert.match(chatInterfaceSource, /微信绑定/)
  assert.match(chatInterfaceSource, /飞书绑定/)
  assert.match(chatInterfaceSource, /channelSubnav/)
})
```

- [ ] **Step 2: 运行测试，确认当前侧栏仍然只有一级按钮**

Run: `cd frontend && node --test tests/branding.test.mjs`

Expected: FAIL，`ChatInterface.tsx` 还没有 `channelNavExpanded`、`channelSubnav` 和二级渠道项。

- [ ] **Step 3: 最小实现二级导航状态、点击规则与侧栏结构**

```tsx
const [channelPage, setChannelPage] =
  useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
const [lastChannelPage, setLastChannelPage] =
  useState<ChannelManagementPage>(DEFAULT_CHANNEL_PAGE)
const [channelNavExpanded, setChannelNavExpanded] = useState(false)

const navigateTo = useCallback(
  (
    nextViewMode: ViewMode,
    nextKnowledgePage: KnowledgePage = DEFAULT_KNOWLEDGE_PAGE,
    nextChannelPage: ChannelManagementPage = channelPage,
    replace = false
  ) => {
    const safeKnowledgePage =
      (
        nextKnowledgePage === 'library-detail' ||
        nextKnowledgePage === 'document-detail'
      ) &&
      !selectedKnowledgeBase
        ? 'libraries'
        : nextKnowledgePage

    setViewMode(nextViewMode)
    setKnowledgePage(safeKnowledgePage)
    setChannelPage(nextChannelPage)
    if (nextViewMode === 'channels') {
      setLastChannelPage(nextChannelPage)
      setChannelNavExpanded(true)
    }
    const nextHash = getRouteHash(nextViewMode, safeKnowledgePage, nextChannelPage)
    if (typeof window === 'undefined') return
    if (window.location.hash === nextHash) return
    if (replace) {
      window.history.replaceState(null, '', nextHash)
    } else {
      window.history.pushState(null, '', nextHash)
    }
  },
  [channelPage, selectedKnowledgeBase]
)

const handleChannelsNavClick = useCallback(() => {
  if (viewMode !== 'channels') {
    const nextPage = resolveChannelEntryPage(undefined, lastChannelPage)
    navigateTo('channels', DEFAULT_KNOWLEDGE_PAGE, nextPage)
    return
  }
  setChannelNavExpanded((current) => !current)
}, [lastChannelPage, navigateTo, viewMode])

<button
  className={`${styles.sidebarButton} ${viewMode === 'channels' ? styles.sidebarButtonActive : ''}`}
  onClick={handleChannelsNavClick}
>
  <span>渠道管理</span>
  <span className={channelNavExpanded ? styles.sidebarChevronExpanded : styles.sidebarChevron}>
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
      onClick={() => navigateTo('channels', DEFAULT_KNOWLEDGE_PAGE, 'weixin')}
    >
      微信绑定
    </button>
    <button
      className={`${styles.channelSubnavItem} ${
        viewMode === 'channels' && channelPage === 'feishu'
          ? styles.channelSubnavItemActive
          : ''
      }`}
      onClick={() => navigateTo('channels', DEFAULT_KNOWLEDGE_PAGE, 'feishu')}
    >
      飞书绑定
    </button>
  </div>
) : null}
```

- [ ] **Step 4: 为子导航补齐样式，形成可收缩的卡片式二级菜单**

```css
.channelSubnav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 2px 0 0 10px;
}

.channelSubnavItem {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  transition: all 0.18s ease;
}

.channelSubnavItemActive {
  border-color: rgba(15, 118, 110, 0.22);
  background: linear-gradient(180deg, rgba(15, 118, 110, 0.12), rgba(15, 118, 110, 0.06));
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
```

- [ ] **Step 5: 重跑导航相关测试，确认侧栏结构已切换为二级导航**

Run: `cd frontend && node --test tests/branding.test.mjs tests/channel-routing.test.mjs`

Expected: PASS，文本结构与 hash 行为测试同时通过。

- [ ] **Step 6: 复核差异，确认知识库、技能、MCP 等一级导航未被误伤**

Run: `git diff -- frontend/components/ChatInterface.tsx frontend/components/ChatInterface.module.css frontend/tests/branding.test.mjs`

Expected: 差异只围绕 `channels` 导航状态、hash 同步和新样式，不影响其他 view 分支的渲染入口。

### Task 3: 把 ChannelManagementView 拆成微信/飞书独立工作台并补测试

**Files:**
- Modify: `frontend/components/chat-interface/ChannelManagementView.tsx`
- Modify: `frontend/components/chat-interface/channelManagement.ts`
- Modify: `frontend/components/chat-interface/types.ts`
- Modify: `frontend/components/ChatInterface.tsx`
- Modify: `frontend/components/ChatInterface.module.css`
- Modify: `frontend/tests/channel-management.test.mjs`

- [ ] **Step 1: 先写失败测试，固定“每次只显示一个渠道工作台”的纯函数行为**

```javascript
test('channel management selects the requested channel bindings only', () => {
  assert.equal(typeof channelManagementPkg.selectBindingsByChannelPage, 'function')

  const bindings = [
    { id: 1, channel: 'weixin_clawbot', runtime_state: { status: 'connected' } },
    { id: 2, channel: 'weixin_clawbot', runtime_state: { status: 'pending' } },
    { id: 3, channel: 'feishu', runtime_state: { status: 'error' } },
  ]

  assert.deepEqual(
    channelManagementPkg.selectBindingsByChannelPage(bindings, 'weixin').map((item) => item.id),
    [1, 2]
  )
  assert.deepEqual(
    channelManagementPkg.selectBindingsByChannelPage(bindings, 'feishu').map((item) => item.id),
    [3]
  )
})

test('channel management creates navigation summaries for each channel child item', () => {
  assert.equal(typeof channelManagementPkg.buildChannelNavItems, 'function')

  const items = channelManagementPkg.buildChannelNavItems([
    { id: 1, channel: 'weixin_clawbot', runtime_state: { status: 'connected' } },
    { id: 2, channel: 'feishu', runtime_state: { status: 'error' } },
  ])

  assert.deepEqual(
    items.map((item) => [item.page, item.total, item.summary.error]),
    [
      ['weixin', 1, 0],
      ['feishu', 1, 1],
    ]
  )
})
```

- [ ] **Step 2: 运行测试，确认当前工具函数还不能支撑二级工作台拆分**

Run: `cd frontend && node --test tests/channel-management.test.mjs`

Expected: FAIL，`selectBindingsByChannelPage()`、`buildChannelNavItems()` 尚不存在。

- [ ] **Step 3: 先补齐渠道工作台所需的纯函数，再用它们驱动页面渲染**

```typescript
export function selectBindingsByChannelPage<T extends ChannelBindingLike>(
  bindings: T[],
  page: ChannelManagementPage
) {
  const channel = page === 'feishu' ? 'feishu' : 'weixin_clawbot'
  return bindings.filter((binding) => binding.channel === channel)
}

export function buildChannelNavItems(bindings: ChannelBindingLike[]) {
  const weixinBindings = selectBindingsByChannelPage(bindings, 'weixin')
  const feishuBindings = selectBindingsByChannelPage(bindings, 'feishu')

  return [
    {
      page: 'weixin' as const,
      label: '微信绑定',
      total: weixinBindings.length,
      summary: summarizeChannelBindings(weixinBindings),
    },
    {
      page: 'feishu' as const,
      label: '飞书绑定',
      total: feishuBindings.length,
      summary: summarizeChannelBindings(feishuBindings),
    },
  ]
}
```

- [ ] **Step 4: 最小重构 `ChannelManagementView`，改为按 `channelPage` 渲染独立工作台**

```tsx
interface ChannelManagementViewProps {
  actor: ActorState
  userId: string
  channelPage: ChannelManagementPage
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
}

const channelBindings = useMemo(
  () => selectBindingsByChannelPage(visibleBindings, channelPage),
  [channelPage, visibleBindings]
)

const channelNavItems = useMemo(
  () => buildChannelNavItems(bindings),
  [bindings]
)

if (channelPage === 'weixin') {
  return (
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>Channel Management</span>
          <h2>微信绑定管理</h2>
          <p>集中管理微信绑定的扫码、状态检查、归属用户和删除。</p>
        </div>
        <div className={styles.managementHeroActions}>
          <button
            className={scope === 'my' ? styles.managementButton : styles.managementMinorButton}
            onClick={() => setScope('my')}
          >
            我的绑定
          </button>
          {canViewAdminScope ? (
            <button
              className={scope === 'all' ? styles.managementButton : styles.managementMinorButton}
              onClick={() => setScope('all')}
            >
              全部绑定
            </button>
          ) : null}
          <button
            className={styles.managementMinorButton}
            disabled={loadingBindings}
            onClick={() => void loadBindings(scope)}
          >
            {loadingBindings ? '刷新中...' : '刷新列表'}
          </button>
        </div>
      </section>
      {renderWeixinWorkspace(channelBindings, channelNavItems)}
    </div>
  )
}

return (
  <div className={styles.managementWorkspace}>
    <section className={styles.managementHero}>
      <div className={styles.managementHeroCopy}>
        <span className={styles.managementHeroEyebrow}>Channel Management</span>
        <h2>飞书绑定管理</h2>
        <p>集中管理飞书绑定的配置、状态、归属用户和删除。</p>
      </div>
      <div className={styles.managementHeroActions}>
        <button
          className={scope === 'my' ? styles.managementButton : styles.managementMinorButton}
          onClick={() => setScope('my')}
        >
          我的绑定
        </button>
        {canViewAdminScope ? (
          <button
            className={scope === 'all' ? styles.managementButton : styles.managementMinorButton}
            onClick={() => setScope('all')}
          >
            全部绑定
          </button>
        ) : null}
        <button
          className={styles.managementMinorButton}
          disabled={loadingBindings}
          onClick={() => void loadBindings(scope)}
        >
          {loadingBindings ? '刷新中...' : '刷新列表'}
        </button>
      </div>
    </section>
    {renderFeishuWorkspace(channelBindings, channelNavItems)}
  </div>
)
```

- [ ] **Step 5: 在 `ChatInterface.tsx` 中传入当前 `channelPage`**

```tsx
<ChannelManagementView
  actor={actor}
  userId={currentUserId}
  channelPage={channelPage}
  requestJson={requestJson}
/>
```

- [ ] **Step 6: 为渠道页头部、详情区和摘要卡补齐样式，不再保留“微信/飞书并排双列”**

```css
.channelWorkspaceHeader {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.channelPageBadge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: var(--accent-primary);
  font-size: 12px;
  font-weight: 700;
}

.channelDetailCard {
  padding: 18px;
  border-radius: var(--radius-xl);
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
}
```

- [ ] **Step 7: 重跑前端单测，确认路由、导航与渠道工具函数全部通过**

Run: `cd frontend && node --test tests/channel-routing.test.mjs tests/channel-management.test.mjs tests/chat-runtime.test.mjs tests/branding.test.mjs`

Expected: PASS，新增渠道工作台测试通过，既有测试无回归。

- [ ] **Step 8: 运行最终前端验证与索引更新**

Run: `cd frontend && pnpm lint`
Expected: PASS

Run: `cd frontend && pnpm build`
Expected: PASS，静态导出成功

Run: `codegraph index --force`
Expected: PASS，索引更新完成

- [ ] **Step 9: 复核最终差异，确认改动只覆盖渠道管理模块**

Run: `git diff -- frontend/components/ChatInterface.tsx frontend/components/ChatInterface.module.css frontend/components/chat-interface/ChannelManagementView.tsx frontend/components/chat-interface/channelManagement.ts frontend/components/chat-interface/types.ts frontend/components/chat-interface/utils.ts frontend/tests`

Expected: 差异集中在渠道路由、侧栏子导航、渠道页拆分和对应测试，不含无关页面改动。
