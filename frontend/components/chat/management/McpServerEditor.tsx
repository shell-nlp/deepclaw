'use client'

import { useEffect, useRef, useState } from 'react'

import styles from '../../ChatInterface.module.css'
import type { McpToolMetadata } from '../utils/types'
import { parseMcpServerJson, validateMcpServerConfig } from '../utils/mcpServerConfig'

export type McpRequest = <T>(path: string, init?: RequestInit) => Promise<T>

interface McpServerEditorProps {
  originalName: string | null
  initialConfig: Record<string, unknown>
  saveError: string
  requestJson: McpRequest
  onClose: () => void
  onSave: (name: string, config: Record<string, unknown>) => void
}

/** 查询单服务工具。Args: requestJson 为鉴权请求函数，name 为服务名，config 为连接配置，signal 为取消信号。 */
export function loadMcpTools(requestJson: McpRequest, name: string, config: Record<string, unknown>, signal: AbortSignal) {
  const { disabled: _disabled, ...server } = config
  return requestJson<McpToolMetadata[]>('/api/mcp/tools', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, server }),
    signal,
  })
}

/** 编辑并测试一个服务。Args: props 为服务初始配置、请求函数和保存关闭回调。 */
export function McpServerEditor({ originalName, initialConfig, saveError, requestJson, onClose, onSave }: McpServerEditorProps) {
  const [name, setName] = useState(originalName ?? '')
  const [inputMode, setInputMode] = useState<'form' | 'json'>('form')
  const [jsonText, setJsonText] = useState('')
  const [baseConfig, setBaseConfig] = useState(initialConfig)
  const [transport, setTransport] = useState(() => {
    const type = String(initialConfig.type ?? (initialConfig.command ? 'stdio' : 'streamable-http'))
    return ['http', 'streamablehttp', 'streamable_http'].includes(type.toLowerCase()) ? 'streamable-http' : type.toLowerCase()
  })
  const [url, setUrl] = useState(String(initialConfig.url ?? ''))
  const [command, setCommand] = useState(String(initialConfig.command ?? ''))
  const [argsText, setArgsText] = useState(JSON.stringify(initialConfig.args ?? []))
  const [headers, setHeaders] = useState<[string, string][]>(() =>
    initialConfig.headers && typeof initialConfig.headers === 'object'
      ? Object.entries(initialConfig.headers).map(([key, value]) => [key, String(value)])
      : [],
  )
  const [showHeaders, setShowHeaders] = useState(false)
  const [error, setError] = useState('')
  const [saveAttempted, setSaveAttempted] = useState(false)
  const [result, setResult] = useState<{ status: 'pending' | 'ok' | 'error'; text: string } | null>(null)
  const test = useRef<AbortController | null>(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose }, [onClose])
  useEffect(() => {
    const previousFocus = document.activeElement
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current()
    }
    window.addEventListener('keydown', handleEscape)
    return () => {
      test.current?.abort()
      window.removeEventListener('keydown', handleEscape)
      if (previousFocus instanceof HTMLElement) previousFocus.focus()
    }
  }, [])

  /** 清除上一次提交和连接结果。Args: 无。 */
  function resetFeedback() {
    test.current?.abort()
    setResult(null)
    setError('')
    setSaveAttempted(false)
  }

  /** 收集并校验当前输入，保留服务的其他设置。Args: validate 为是否执行完整校验。 */
  function collectConfig(validate = true) {
    if (inputMode === 'json') return parseMcpServerJson(jsonText, name)
    const server = { ...baseConfig }
    if (transport !== String(baseConfig.type ?? '').toLowerCase()) server.type = transport
    if (transport === 'stdio') {
      server.command = command.trim()
      let args: unknown
      try { args = JSON.parse(argsText) } catch { throw new Error('启动参数必须是 JSON 字符串数组。') }
      if (Array.isArray(args) && (args.length || 'args' in server)) server.args = args
      else if (!Array.isArray(args)) server.args = args
      delete server.url
      delete server.headers
      if (!baseConfig.type && baseConfig.command) delete server.type
    } else {
      server.url = url.trim()
      delete server.command
      delete server.args
      const requestHeaders = headers.filter(([key, value]) => key || value).map(([key, value]) => [key.trim(), value])
      const names = requestHeaders.map(([key]) => key.toLowerCase())
      if (new Set(names).size !== names.length) throw new Error('请求头名称不能重复。')
      if (requestHeaders.length) server.headers = Object.fromEntries(requestHeaders)
      else delete server.headers
    }
    return validate ? validateMcpServerConfig(name, server) : { serviceName: name.trim(), server }
  }

  /** 切换输入方式并同步当前草稿。Args: mode 为目标输入方式。 */
  function switchInputMode(mode: 'form' | 'json') {
    if (mode === inputMode) return
    resetFeedback()
    try {
      if (mode === 'json') {
        const { serviceName, server } = collectConfig(false)
        setJsonText(JSON.stringify(serviceName ? { mcpServers: { [serviceName]: server } } : server, null, 2))
      } else {
        const { serviceName, server } = parseMcpServerJson(jsonText, name)
        setName(serviceName)
        setBaseConfig(server)
        const type = String(server.type ?? (server.command ? 'stdio' : 'streamable-http')).toLowerCase()
        setTransport(['http', 'streamablehttp', 'streamable_http'].includes(type) ? 'streamable-http' : type)
        setUrl(String(server.url ?? ''))
        setCommand(String(server.command ?? ''))
        setArgsText(JSON.stringify(server.args ?? []))
        setHeaders(Object.entries(server.headers ?? {}).map(([key, value]) => [key, String(value)]))
      }
      setInputMode(mode)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '请检查服务配置。')
    }
  }

  /** 使用当前草稿保存或测试。Args: action 为保存或测试操作。 */
  async function submit(action: 'save' | 'test') {
    resetFeedback()
    try {
      const { serviceName, server } = collectConfig()
      if (action === 'save') {
        setSaveAttempted(true)
        onSave(serviceName, server)
        return
      }
      const controller = new AbortController()
      test.current = controller
      setResult({ status: 'pending', text: '正在测试连接…' })
      try {
        const tools = await loadMcpTools(requestJson, serviceName, server, controller.signal)
        if (!controller.signal.aborted) setResult({ status: 'ok', text: `连接成功，发现 ${tools.length} 个工具。` })
      } catch (cause) {
        if (!controller.signal.aborted) setResult({
          status: 'error',
          text: cause instanceof Error ? cause.message : '无法连接服务。',
        })
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '请检查服务配置。')
    }
  }

  return (
    <div className={styles.extensionDialogOverlay} onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <form className={`${styles.extensionDialog} ${styles.mcpServerEditor}`} role="dialog" aria-modal="true"
        aria-labelledby="mcp-server-editor-title" onChange={resetFeedback} onSubmit={(event) => {
          event.preventDefault()
          void submit('save')
        }}>
        <div className={styles.extensionDialogHeader}>
          <h3 id="mcp-server-editor-title">{originalName === null ? '新增 MCP 服务' : '编辑 MCP 服务'}</h3>
          <button type="button" className={styles.extensionIconButton} onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className={`${styles.extensionDialogUtilities} ${styles.mcpEditorModes}`} role="group" aria-label="配置输入方式">
          <button type="button" aria-pressed={inputMode === 'form'} onClick={() => switchInputMode('form')}>表单配置</button>
          <button type="button" aria-pressed={inputMode === 'json'} onClick={() => switchInputMode('json')}>JSON 配置</button>
        </div>
        {inputMode === 'json' ? (
          <div className={styles.mcpEditorFields}>
            <label>服务名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="直接填写连接对象时必填" /></label>
            <p className={styles.extensionDialogHint}>支持包含一个服务的 mcpServers JSON，自动读取服务名；也可直接填写连接对象并在上方命名。多个服务请使用批量编辑。</p>
            <label>服务 JSON 配置<textarea className={styles.extensionCodeEditor} value={jsonText}
              onChange={(event) => setJsonText(event.target.value)} spellCheck={false} autoFocus
              placeholder={'{"mcpServers":{"example":{"type":"streamable-http","url":"http://192.168.1.10:8000/mcp"}}}'} /></label>
          </div>
        ) : <div className={styles.mcpEditorFields}>
          <div className={styles.mcpEditorIdentity}>
            <label>服务名称<input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 catalog" /></label>
            <label>连接方式
              <select value={transport} onChange={(event) => setTransport(event.target.value)}>
                {!['streamable-http', 'sse', 'stdio'].includes(transport) && <option value={transport}>{transport}</option>}
                <option value="streamable-http">Streamable HTTP</option>
                <option value="sse">SSE</option>
                <option value="stdio">stdio</option>
              </select>
            </label>
          </div>
          {transport === 'stdio' ? (
            <>
              <label>启动命令<input value={command} onChange={(event) => setCommand(event.target.value)} /></label>
              <label>启动参数（JSON 数组）<input value={argsText} onChange={(event) => setArgsText(event.target.value)} /></label>
              <p className={styles.extensionDialogHint}>连接测试需要匹配管理员在服务端配置的 stdio 服务。</p>
            </>
          ) : (
            <>
              <label>服务地址<input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/mcp" spellCheck={false} /></label>
              <fieldset className={styles.mcpEditorHeaders}>
                <legend>请求头 <span>可选</span></legend>
                {headers.map(([key, value], index) => (
                  <div className={styles.mcpEditorHeaderRow} key={index}>
                    <input aria-label={`请求头名称 ${index + 1}`} value={key} placeholder="Authorization"
                      spellCheck={false} onChange={(event) => setHeaders(headers.map((header, row) => row === index ? [event.target.value, value] : header))} />
                    <input aria-label={`请求头值 ${index + 1}`} value={value} type={showHeaders ? 'text' : 'password'}
                      placeholder="请求头值" autoComplete="off" spellCheck={false}
                      onChange={(event) => setHeaders(headers.map((header, row) => row === index ? [key, event.target.value] : header))} />
                    <button type="button" className={styles.extensionIconButton} aria-label={`移除请求头 ${index + 1}`} onClick={() => {
                      setHeaders(headers.filter((_, row) => row !== index))
                      resetFeedback()
                    }}>×</button>
                  </div>
                ))}
                <div className={styles.mcpHeaderActions}>
                  <button type="button" className={styles.extensionTextButton} onClick={() => setHeaders([...headers, ['', '']])}>＋ 添加请求头</button>
                  {headers.length > 0 && <button type="button" className={styles.extensionTextButton} onClick={() => setShowHeaders(!showHeaders)}>
                    {showHeaders ? '隐藏值' : '显示值'}
                  </button>}
                </div>
              </fieldset>
            </>
          )}
        </div>}
        {(error || (saveAttempted && saveError)) && <div className={styles.managementError} role="alert">{error || saveError}</div>}
        {result && <div className={result.status === 'error' ? styles.managementError : styles.managementNotice}
          role={result.status === 'error' ? 'alert' : 'status'}>{result.text}</div>}
        <div className={styles.extensionDialogFooter}>
          <button type="button" className={styles.extensionSecondaryButton} disabled={result?.status === 'pending'} onClick={() => void submit('test')}>
            {result?.status === 'pending' ? '测试中…' : '测试连接'}
          </button>
          <div className={styles.extensionDialogActions}>
            <button type="button" className={styles.extensionSecondaryButton} onClick={onClose}>取消</button>
            <button type="submit" className={styles.extensionPrimaryButton}>保存服务</button>
          </div>
        </div>
      </form>
    </div>
  )
}
