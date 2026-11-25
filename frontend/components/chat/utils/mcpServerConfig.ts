/** 校验单个服务的连接配置。Args: name 为服务名，config 为当前草稿。 */
export function validateMcpServerConfig(name: string, config: Record<string, unknown>) {
  const serviceName = name.trim()
  if (!serviceName || serviceName.length > 256) throw new Error('请填写服务名称，最多 256 个字符。')
  const transport = String(config.type ?? (config.command ? 'stdio' : 'streamable-http')).toLowerCase()
  if (transport === 'stdio') {
    if (typeof config.command !== 'string' || !config.command.trim()) throw new Error('请填写启动命令。')
    if (config.args !== undefined && (!Array.isArray(config.args) || config.args.some((value) => typeof value !== 'string'))) {
      throw new Error('启动参数必须是 JSON 字符串数组。')
    }
  } else {
    if (!['http', 'streamablehttp', 'streamable_http', 'streamable-http', 'sse'].includes(transport)) {
      throw new Error('请选择支持的连接方式。')
    }
    let endpoint: URL
    try { endpoint = new URL(String(config.url ?? '').trim()) } catch { throw new Error('请填写有效的 HTTP 或 HTTPS 地址。') }
    if (!['http:', 'https:'].includes(endpoint.protocol) || endpoint.username || endpoint.password) {
      throw new Error('请填写有效的 HTTP 或 HTTPS 地址。')
    }
    if (config.headers !== undefined) {
      if (!config.headers || typeof config.headers !== 'object' || Array.isArray(config.headers)) {
        throw new Error('请求头必须是 JSON 对象。')
      }
      const names = new Set<string>()
      for (const [key, value] of Object.entries(config.headers)) {
        if (!/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(key) || typeof value !== 'string' || /[\r\n]/.test(value)) {
          throw new Error('请检查请求头，名称必须有效，值只能占一行。')
        }
        if (names.has(key.toLowerCase())) throw new Error('请求头名称不能重复。')
        names.add(key.toLowerCase())
      }
    }
  }
  return { serviceName, server: config }
}

/** 解析单服务 JSON，兼容标准 mcpServers 包装和直接连接对象。Args: text 为 JSON 草稿，name 为直接对象的服务名。 */
export function parseMcpServerJson(text: string, name: string) {
  let parsed: unknown
  try { parsed = JSON.parse(text) } catch { throw new Error('MCP 配置不是合法 JSON，请先修正后再保存。') }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('MCP 配置必须是 JSON 对象。')
  const config = parsed as Record<string, unknown>
  const root = config.mcpServers ?? config.mcpServer
  if (root !== undefined) {
    if (!root || typeof root !== 'object' || Array.isArray(root)) throw new Error('mcpServers 必须是 JSON 对象。')
    const entries = Object.entries(root)
    if (entries.length !== 1) throw new Error('此处每次只能新增或编辑一个服务，多个服务请使用批量编辑。')
    const [serviceName, server] = entries[0]
    if (!server || typeof server !== 'object' || Array.isArray(server)) throw new Error('服务连接配置必须是 JSON 对象。')
    return validateMcpServerConfig(serviceName, server as Record<string, unknown>)
  }
  return validateMcpServerConfig(name, config)
}
