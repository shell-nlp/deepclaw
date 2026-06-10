import test from 'node:test'
import assert from 'node:assert/strict'

import * as channelManagementPkg from '../components/chat-interface/channelManagement.ts'

test('channel management bootstrap only loads bound users on initial view', () => {
  assert.equal(
    typeof channelManagementPkg.getChannelManagementBootstrapActions,
    'function'
  )
  assert.deepEqual(
    channelManagementPkg.getChannelManagementBootstrapActions('demo-user'),
    {
      loadBoundUsers: true,
      generateQrcodeUserId: null,
    }
  )
})

test('channel management uses direct image url without regenerating payload', () => {
  assert.equal(typeof channelManagementPkg.getChannelManagementQrRenderState, 'function')
  assert.deepEqual(
    channelManagementPkg.getChannelManagementQrRenderState({
      qrcode: '1234567890',
      qrcodeUrl: 'https://example.test/qrcode.png',
      generatedDataUrl: 'data:image/png;base64,local',
    }),
    {
      imageSrc: 'https://example.test/qrcode.png',
      shouldGenerateDataUrl: false,
      payload: '1234567890',
    }
  )
})

test('channel management regenerates qrcode when upstream url is an html page', () => {
  assert.deepEqual(
    channelManagementPkg.getChannelManagementQrRenderState({
      qrcode: '1234567890',
      qrcodeUrl:
        'https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=1234567890&bot_type=3',
      generatedDataUrl: 'data:image/png;base64,local',
    }),
    {
      imageSrc: 'data:image/png;base64,local',
      shouldGenerateDataUrl: true,
      payload:
        'https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=1234567890&bot_type=3',
    }
  )
})

test('channel management groups bindings by channel and summarizes counts', () => {
  assert.equal(typeof channelManagementPkg.groupBindingsByChannel, 'function')
  assert.equal(typeof channelManagementPkg.summarizeChannelBindings, 'function')

  const bindings = [
    {
      id: 1,
      channel: 'weixin_clawbot',
      display_name: '张三主号',
      status: 'active',
      runtime_state: { status: 'connected' },
    },
    {
      id: 2,
      channel: 'weixin_clawbot',
      display_name: '李四代绑号',
      status: 'active',
      runtime_state: { status: 'pending' },
    },
    {
      id: 3,
      channel: 'feishu',
      display_name: '市场部机器人',
      status: 'error',
      runtime_state: { status: 'error' },
    },
  ]

  const groups = channelManagementPkg.groupBindingsByChannel(bindings)
  const weixinSummary = channelManagementPkg.summarizeChannelBindings(
    groups.weixin_clawbot
  )

  assert.equal(groups.weixin_clawbot.length, 2)
  assert.equal(groups.feishu.length, 1)
  assert.deepEqual(weixinSummary, {
    total: 2,
    connected: 1,
    pending: 1,
    error: 0,
  })
})

test('channel management filters admin overview rows by owner and channel', () => {
  assert.equal(
    typeof channelManagementPkg.filterBindingsForAdminOverview,
    'function'
  )

  const rows = channelManagementPkg.filterBindingsForAdminOverview(
    [
      {
        id: 1,
        channel: 'weixin_clawbot',
        owner_user_id: 'zhangsan',
        status: 'active',
        display_name: '张三主号',
        runtime_state: { status: 'connected' },
      },
      {
        id: 2,
        channel: 'feishu',
        owner_user_id: 'zhangsan',
        status: 'error',
        display_name: '市场部机器人',
        runtime_state: { status: 'error' },
      },
      {
        id: 3,
        channel: 'feishu',
        owner_user_id: 'lisi',
        status: 'active',
        display_name: '客服值班号',
        runtime_state: { status: 'connected' },
      },
    ],
    { ownerUserId: 'zhangsan', channel: 'feishu', status: '' }
  )

  assert.deepEqual(
    rows.map((item) => item.id),
    [2]
  )
})

test('channel management normalizes collaborative binding owner input', () => {
  assert.equal(
    channelManagementPkg.normalizeBindingOwnerUserId('  zhangsan  ', 'lisi'),
    'zhangsan'
  )
  assert.equal(
    channelManagementPkg.normalizeBindingOwnerUserId('   ', 'lisi'),
    'lisi'
  )
})

test('channel management reuses qrcode cache object when payloads are unchanged', () => {
  assert.equal(typeof channelManagementPkg.mergeGeneratedQrcodes, 'function')

  const current = {
    1: 'data:image/png;base64,a',
  }

  assert.equal(
    channelManagementPkg.mergeGeneratedQrcodes(current, {
      1: 'data:image/png;base64,a',
    }),
    current
  )

  assert.deepEqual(channelManagementPkg.mergeGeneratedQrcodes(current, {}), current)
  assert.deepEqual(channelManagementPkg.mergeGeneratedQrcodes(current, { 2: 'b' }), {
    1: 'data:image/png;base64,a',
    2: 'b',
  })
})

test('channel management selects the requested channel bindings only', () => {
  assert.equal(typeof channelManagementPkg.selectBindingsByChannelPage, 'function')

  const bindings = [
    { id: 1, channel: 'weixin_clawbot', runtime_state: { status: 'connected' } },
    { id: 2, channel: 'weixin_clawbot', runtime_state: { status: 'pending' } },
    { id: 3, channel: 'feishu', runtime_state: { status: 'error' } },
  ]

  assert.deepEqual(
    channelManagementPkg.selectBindingsByChannelPage(bindings, 'weixin').map(
      (item) => item.id
    ),
    [1, 2]
  )
  assert.deepEqual(
    channelManagementPkg.selectBindingsByChannelPage(bindings, 'feishu').map(
      (item) => item.id
    ),
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

test('channel management groups bindings into owner rows for per-user channel management', () => {
  assert.equal(typeof channelManagementPkg.buildBindingOwnerRows, 'function')

  const rows = channelManagementPkg.buildBindingOwnerRows([
    {
      id: 1,
      channel: 'weixin_clawbot',
      owner_user_id: 'zhangsan',
      manager_user_id: 'admin-a',
      updated_at: '2026-06-10T10:00:00Z',
      status: 'active',
      runtime_state: { status: 'connected' },
    },
    {
      id: 2,
      channel: 'weixin_clawbot',
      owner_user_id: 'zhangsan',
      manager_user_id: 'admin-b',
      updated_at: '2026-06-10T11:00:00Z',
      status: 'active',
      runtime_state: { status: 'pending' },
    },
    {
      id: 3,
      channel: 'weixin_clawbot',
      owner_user_id: 'lisi',
      manager_user_id: 'admin-a',
      updated_at: '2026-06-10T09:30:00Z',
      status: 'error',
      runtime_state: { status: 'error' },
    },
  ])

  assert.deepEqual(rows, [
    {
      ownerUserId: 'zhangsan',
      total: 2,
      displayNames: [],
      summary: {
        total: 2,
        connected: 1,
        pending: 1,
        error: 0,
      },
      latestUpdatedAt: '2026-06-10T11:00:00Z',
      managerUserIds: ['admin-a', 'admin-b'],
    },
    {
      ownerUserId: 'lisi',
      total: 1,
      displayNames: [],
      summary: {
        total: 1,
        connected: 0,
        pending: 0,
        error: 1,
      },
      latestUpdatedAt: '2026-06-10T09:30:00Z',
      managerUserIds: ['admin-a'],
    },
  ])
})
