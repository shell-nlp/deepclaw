import { useEffect, useState } from 'react'
import DOMPurify from 'dompurify'

import chatStyles from '../../ChatInterface.module.css'
import { parseMarkdown } from '../utils'
import { readChatMarkdown } from '../utils/chatFiles'
import styles from './FileKnowledgeView.module.css'

/** 预览同一 Markdown 文件的渲染结果与原文。Args: path 为原件地址，withAuthHeaders 提供认证头。 */
export function FileMarkdownPreview({ path, withAuthHeaders }: {
  path: string
  withAuthHeaders: () => HeadersInit
}) {
  const [showSource, setShowSource] = useState(false)
  const [document, setDocument] = useState<{ source: string; html: string } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setDocument(null)
    setError('')
    void readChatMarkdown(path, withAuthHeaders(), controller.signal)
      .then((source) => {
        if (controller.signal.aborted) return
        const html = DOMPurify.sanitize(parseMarkdown(source), {
          USE_PROFILES: { html: true },
          FORBID_TAGS: ['form', 'style'],
          FORBID_ATTR: ['style', 'id', 'name'],
        })
        setDocument({ source, html })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setError(error instanceof Error ? error.message : 'Markdown 预览加载失败。')
        }
      })
    return () => controller.abort()
  }, [path, withAuthHeaders])

  return <>
    <div className={styles.markdownControls}>
      <div className={styles.collections} role="group" aria-label="Markdown 查看方式">
        <button type="button" aria-pressed={!showSource} onClick={() => setShowSource(false)}>渲染</button>
        <button type="button" aria-pressed={showSource} onClick={() => setShowSource(true)}>源格式</button>
      </div>
    </div>
    {error ? <p className={styles.error} role="alert">{error}</p> :
      !document ? <p className={styles.empty} role="status">正在加载预览…</p> :
      !document.source ? <p className={styles.empty}>此文件没有内容。</p> :
      showSource ? <pre className={styles.markdownSource}><code>{document.source}</code></pre> :
      <article className={`${chatStyles.messageContent} ${styles.markdownBody}`}
        dangerouslySetInnerHTML={{ __html: document.html }} />}
  </>
}
