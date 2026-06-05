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
