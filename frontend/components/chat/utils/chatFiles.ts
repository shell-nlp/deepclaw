import { getApiUrl } from './index'

export const CHAT_FILE_TYPES = '.docx,.txt,.md,.pdf,.xlsx'
const CHAT_FILE_PATH = /^\/api\/files\/[a-f0-9]{32}\/download$/

export type ChatFile = {
  file_id: string
  name: string
  extension: string
  size: number
  created_at: string
  favorite: boolean
  download_url: string
}

/** 上传聊天附件。Args: file 为原件，headers 为当前账号的认证头。 */
export async function uploadChatFile(file: File, headers: HeadersInit): Promise<ChatFile> {
  if (file.size > 20 * 1024 * 1024) throw new Error('单个文件最多 20 MiB。')
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
