import { getApiUrl } from './index'

export const CHAT_FILE_TYPES = '.docx,.txt,.md,.pdf,.xlsx'
export const CHAT_ATTACHMENTS_HEADING = '聊天附件（链接中的 ID 用于文件工具）'
const CHAT_FILE_PATH = /^\/api\/files\/[a-f0-9]{32}\/download$/

/** 从用户消息末尾提取聊天附加的文件，供历史消息和即时消息共用。
 *
 * Args:
 *   content: 包含用户正文和可选附件区块的原始消息。
 */
export function splitChatAttachments(content: string) {
  const separator = `\n\n${CHAT_ATTACHMENTS_HEADING}\n\n`
  const boundary = content.lastIndexOf(separator)
  const attachments: { name: string; path: string }[] = []
  if (boundary < 0) return { text: content, attachments }

  for (const entry of content.slice(boundary + separator.length).split('\n\n')) {
    const match = /^- \[([\s\S]+)\]\(([^\s()]+)\)$/.exec(entry)
    if (!match || !isChatFileLink(match[2])) return { text: content, attachments: [] }
    const [, label, path] = match
    const name = label.replace(/\\([\\\[\]`*_])/g, '$1')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
    attachments.push({ name, path })
  }

  return { text: content.slice(0, boundary), attachments }
}

export type ChatFile = {
  file_id: string
  name: string
  extension: string
  size: number
  created_at: string
  favorite: boolean
  download_url: string
  reused?: boolean
}

/** 计算上传预检指纹，浏览器不支持时交给服务端去重。 */
export async function getFileFingerprint(file: File) {
  if (!globalThis.crypto?.subtle) return null
  const name = file.name.trim()
  const dot = name.lastIndexOf('.')
  try {
    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
    return {
      extension: dot > 0 ? name.slice(dot).toLowerCase() : '',
      size: file.size,
      sha256: Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join(''),
    }
  } catch {
    return null
  }
}

/** 上传聊天附件。Args: file 为原件，headers 为当前账号的认证头。 */
export async function uploadChatFile(file: File, headers: HeadersInit): Promise<ChatFile> {
  if (file.size > 20 * 1024 * 1024) throw new Error('单个文件最多 20 MiB。')
  const fingerprint = await getFileFingerprint(file)
  if (fingerprint) {
    const checkHeaders = new Headers(headers)
    checkHeaders.set('Content-Type', 'application/json')
    try {
      const check = await fetch(getApiUrl('/api/files/upload-check'), {
        method: 'POST', headers: checkHeaders, body: JSON.stringify(fingerprint),
      })
      if (check.ok) {
        const existing = await check.json() as ChatFile | null
        if (existing?.reused) return existing
      }
    } catch {
      // 预检失败时继续上传，由服务端计算摘要。
    }
  }
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(getApiUrl('/api/files'), { method: 'POST', headers, body })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(typeof data?.detail === 'string' ? data.detail : '文件上传失败。')
  }
  return response.json()
}

/** 下载当前账号的文件。Args: path 为文件地址，headers 为认证头。 */
export async function downloadChatFile(path: string, headers: HeadersInit) {
  const response = await fetchChatFile(path, headers)
  const disposition = response.headers.get('Content-Disposition')
  const name = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name ? decodeURIComponent(name) : '附件'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** 读取 Markdown 原件，兼容上传时支持的编码。Args: path 为文件地址，headers 为认证头，signal 用于取消。 */
export async function readChatMarkdown(path: string, headers: HeadersInit, signal: AbortSignal) {
  const response = await fetchChatFile(path, headers, signal)
  const bytes = await response.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return new TextDecoder('gb18030', { fatal: true }).decode(bytes)
  }
}

/** 请求已授权的文件原件。Args: path 为文件地址，headers 为认证头，signal 用于取消。 */
async function fetchChatFile(path: string, headers: HeadersInit, signal?: AbortSignal) {
  if (!isChatFileLink(path)) throw new Error('无效的文件地址。')
  const response = await fetch(getApiUrl(path), { headers, signal })
  if (!response.ok) throw new Error('无法读取文件，请检查登录状态和文件权限。')
  return response
}

/** 判断是否为站内聊天文件链接。Args: path 为消息链接原始地址。 */
export function isChatFileLink(path: string) {
  return CHAT_FILE_PATH.test(path)
}
