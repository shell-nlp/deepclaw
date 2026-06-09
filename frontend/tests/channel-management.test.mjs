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
