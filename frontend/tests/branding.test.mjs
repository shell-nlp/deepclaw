import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const frontendRoot = resolve(import.meta.dirname, '..')

function readFrontendFile(relativePath) {
  return readFileSync(resolve(frontendRoot, relativePath), 'utf8')
}

test('frontend metadata and shell branding use DeepClaw', () => {
  const layoutSource = readFrontendFile('app/layout.tsx')
  const chatInterfaceSource = readFrontendFile('components/ChatInterface.tsx')
  const chatViewSource = readFrontendFile('components/chat-interface/ChatView.tsx')
  const loginPageSource = readFrontendFile('app/login/page.tsx')

  assert.match(layoutSource, /title:\s*['"]DeepClaw['"]/)
  assert.doesNotMatch(layoutSource, /AI Agent Chat/)

  assert.match(chatInterfaceSource, /<h1 className=\{styles\.title\}>DeepClaw<\/h1>/)
  assert.doesNotMatch(chatInterfaceSource, /AI Agent Chat/)

  assert.match(chatViewSource, /欢迎使用 DeepClaw/)
  assert.doesNotMatch(chatViewSource, /欢迎使用 AI Agent Chat/)

  assert.match(loginPageSource, /<h1>DeepClaw<\/h1>/)
  assert.doesNotMatch(loginPageSource, /AI Agent Chat/)
})

test('chat interface renders expandable channel navigation with child items', () => {
  const chatInterfaceSource = readFrontendFile('components/ChatInterface.tsx')

  assert.match(chatInterfaceSource, /channelNavExpanded/)
  assert.match(chatInterfaceSource, /微信绑定/)
  assert.match(chatInterfaceSource, /飞书绑定/)
  assert.match(chatInterfaceSource, /channelSubnav/)
})

test('channel navigation chevron does not affect centered sidebar label layout', () => {
  const stylesSource = readFrontendFile('components/ChatInterface.module.css')

  assert.match(stylesSource, /\.sidebarButton\s*\{[^}]*position:\s*relative;/s)
  assert.match(
    stylesSource,
    /\.sidebarChevron,\s*\.sidebarChevronExpanded\s*\{[^}]*position:\s*absolute;[^}]*right:\s*12px;[^}]*margin-left:\s*0;/s
  )
})

test('single channel management view does not render cross-channel summary cards', () => {
  const channelManagementSource = readFrontendFile(
    'components/chat-interface/ChannelManagementView.tsx'
  )

  assert.doesNotMatch(channelManagementSource, /managementSummaryGrid/)
  assert.doesNotMatch(channelManagementSource, /channelNavItems\.filter/)
  assert.doesNotMatch(
    channelManagementSource,
    /在线\s*\{[^}]+\}\s*\/\s*待处理\s*\{[^}]+\}\s*\/\s*异常/
  )
})

test('single channel management view renders a bound user section before binding details', () => {
  const channelManagementSource = readFrontendFile(
    'components/chat-interface/ChannelManagementView.tsx'
  )

  assert.match(channelManagementSource, /已绑定用户/)
  assert.match(channelManagementSource, /绑定实例明细/)
  assert.match(channelManagementSource, /selectedOwnerBindings/)
})

test('single channel management view selects one binding instance before showing details', () => {
  const channelManagementSource = readFrontendFile(
    'components/chat-interface/ChannelManagementView.tsx'
  )

  assert.match(channelManagementSource, /selectedBindingId/)
  assert.match(channelManagementSource, /selectedBinding/)
  assert.match(channelManagementSource, /选择绑定实例/)
})
