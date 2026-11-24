export interface ChatImage {
  name: string
  url: string
}

export const CHAT_IMAGE_TYPES = 'image/png,image/jpeg,image/webp'
const IMAGE_PREFIX = /^data:(image\/(?:png|jpeg|webp));base64,/

/** 读取一张本地图片。Args: file 为待上传文件。 */
export async function readChatImage(file: File): Promise<ChatImage> {
  if (!CHAT_IMAGE_TYPES.split(',').includes(file.type)) {
    throw new Error('请选择 PNG、JPEG 或 WebP 图片。')
  }
  if (file.size > 5 * 1024 * 1024 || file.size === 0) {
    throw new Error('图片不能为空，单张最多 5 MB。')
  }
  const url = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('读取图片失败，请重新选择。'))
    reader.readAsDataURL(file)
  })
  return { name: file.name, url }
}

/** 从会话记录恢复图片预览。Args: content 为用户消息内容。 */
export function historyChatImages(content: unknown): ChatImage[] {
  if (!Array.isArray(content)) return []
  return content.flatMap((block) => {
    const url = block?.type === 'image_url' ? block.image_url?.url
      : block?.type === 'image' && block.source?.type === 'data'
        ? 'data:' + (block.source.mimeType ?? block.source.mime_type) + ';base64,' + block.source.value
        : ''
    return typeof url === 'string' && IMAGE_PREFIX.test(url) ? [{ name: '聊天图片', url }] : []
  })
}
