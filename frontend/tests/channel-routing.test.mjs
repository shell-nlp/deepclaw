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
