import test from 'node:test'
import assert from 'node:assert/strict'
import { parseMcpServerJson, validateMcpServerConfig } from '../components/chat/utils/mcpServerConfig.ts'

test('single-service JSON reads its name and preserves extra settings', () => {
  const server = { type: 'streamable-http', url: 'http://10.87.18.144:31113/mcp', headers: { Authorization: 'Bearer example' }, disabled: true }
  assert.deepEqual(parseMcpServerJson(JSON.stringify({ mcpServers: { internal: server } }), ''), { serviceName: 'internal', server })
  assert.deepEqual(parseMcpServerJson(JSON.stringify(server), ' internal '), { serviceName: 'internal', server })
})

test('JSON supports stdio environment and rejects multiple services', () => {
  const server = { command: 'npx', args: ['-y', 'example'], env: { MODE: 'test' } }
  assert.deepEqual(parseMcpServerJson(JSON.stringify({ mcpServers: { local: server } }), ''), { serviceName: 'local', server })
  assert.throws(() => parseMcpServerJson(JSON.stringify({ mcpServers: { one: server, two: server } }), ''), /每次只能/)
})

test('JSON errors and connection validation apply to both input modes', () => {
  for (const text of ['{', '[]', 'null', '{"mcpServers":[]}']) assert.throws(() => parseMcpServerJson(text, 'demo'))
  for (const server of [
    { url: 'file:///tmp/test' },
    { url: 'http://user:password@example.com' },
    { command: 'npx', args: [42] },
    { url: 'http://localhost/mcp', headers: { Authorization: 'a', authorization: 'b' } },
    { url: 'http://localhost/mcp', headers: { Test: 'a\nb' } },
  ]) {
    assert.throws(() => validateMcpServerConfig('demo', server))
    assert.throws(() => parseMcpServerJson(JSON.stringify(server), 'demo'))
  }
  assert.throws(() => parseMcpServerJson('{"url":"http://localhost/mcp"}', ''), /服务名称/)
})
