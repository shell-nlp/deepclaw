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
