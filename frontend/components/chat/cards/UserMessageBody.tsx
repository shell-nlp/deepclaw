import { memo, useState } from 'react'
import styles from '../../ChatInterface.module.css'
import { buildAuthorizationHeaders, getStoredAuthToken } from '../utils/auth'
import { downloadChatFile, splitChatAttachments } from '../utils/chatFiles'
import type { Message } from '../utils/types'
import { MarkdownMessage } from './AssistantMessageBody'

/** 渲染用户图片、文件卡片和正文。
 *
 * Args:
 *   message: 用户即时发送或从历史会话恢复的消息。
 */
export const UserMessageBody = memo(function UserMessageBody({ message }: { message: Message }) {
  const { text, attachments } = splitChatAttachments(message.content)
  const [downloadError, setDownloadError] = useState('')

  return (
    <>
      {message.images?.length ? (
        <div className={styles.chatMessageImages}>
          {message.images.map((image, index) => <img key={index} src={image.url} alt={image.name} />)}
        </div>
      ) : null}
      {attachments.length > 0 && (
        <div className={styles.messageAttachments}>
          {attachments.map(({ name, path }, index) => (
            <button
              key={`${path}-${index}`}
              type="button"
              className={styles.messageAttachment}
              title={name}
              aria-label={`下载 ${name}`}
              onClick={() => {
                setDownloadError('')
                void downloadChatFile(path, buildAuthorizationHeaders(getStoredAuthToken()))
                  .catch((error: Error) => setDownloadError(error.message))
              }}
            >
              <span className={styles.messageAttachmentIcon} aria-hidden="true" />
              <span className={styles.messageAttachmentInfo}>
                <span className={styles.messageAttachmentName}>{name}</span>
                <span className={styles.messageAttachmentType}>{name.split('.').pop()?.toUpperCase()}</span>
              </span>
            </button>
          ))}
          {downloadError && <p className={styles.composerImageError} role="alert">{downloadError}</p>}
        </div>
      )}
      {text && <MarkdownMessage content={text} />}
    </>
  )
})
