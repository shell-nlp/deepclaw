import { useEffect, useRef, useState } from 'react'

import { CHAT_FILE_TYPES, downloadChatFile, uploadChatFile, type ChatFile } from '../utils/chatFiles'
import { formatDateTime } from '../utils'
import { FileMarkdownPreview } from './FileMarkdownPreview'
import styles from './FileKnowledgeView.module.css'

type FilePage = { files: ChatFile[]; next_offset: number | null }
type Retention = { retention_days: number | null }
type Cell = { value: string | number | boolean | null; formula?: string | null }
type Preview = {
  sheet: string | null
  sheets?: { name: string; total_lines: number }[]
  total_lines: number
  lines: { line: number; content?: string; page?: number; cells?: Record<string, Cell>; truncated?: boolean }[]
  next_start_line: number | null
  pages_without_text?: number[]
}

/** 显示并预览当前账号的上传文件和模型产物。Args: 请求、鉴权及当前账号的权限。 */
export function FileKnowledgeView({ canRead, canWrite, isGuest, requestJson, withAuthHeaders }: {
  canRead: boolean
  canWrite: boolean
  isGuest: boolean
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>
  withAuthHeaders: () => HeadersInit
}) {
  const input = useRef<HTMLInputElement>(null)
  const [offset, setOffset] = useState(0)
  const [favorites, setFavorites] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [page, setPage] = useState<FilePage | null>(null)
  const [listError, setListError] = useState('')
  const [actionError, setActionError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [moving, setMoving] = useState(false)
  const [retention, setRetention] = useState<Retention | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [retentionDraft, setRetentionDraft] = useState('')
  const [savingRetention, setSavingRetention] = useState(false)
  const [selected, setSelected] = useState<ChatFile | null>(null)
  const [sheet, setSheet] = useState('')
  const [starts, setStarts] = useState([1])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState('')
  const isMarkdown = selected?.extension.toLowerCase() === '.md'
  const start = starts.at(-1) ?? 1

  useEffect(() => {
    if (!canRead) return
    let active = true
    setPage(null)
    setListError('')
    void requestJson<FilePage>(`/api/files?offset=${offset}&favorite=${favorites}`).then(
      (data) => { if (active) setPage(data) },
      (error: Error) => { if (active) setListError(error.message) },
    )
    return () => { active = false }
  }, [canRead, favorites, offset, refresh, requestJson])

  useEffect(() => {
    if (!canRead) return
    let active = true
    void requestJson<Retention>('/api/files/retention').then(
      (data) => {
        if (!active) return
        setRetention(data)
        setRetentionDraft(data.retention_days?.toString() ?? '')
      },
      (error: Error) => { if (active) setActionError(error.message) },
    )
    return () => { active = false }
  }, [canRead, requestJson])

  useEffect(() => {
    if (!canRead || !selected || isMarkdown) return
    let active = true
    const params = new URLSearchParams({ start_line: String(start), limit: '50' })
    if (sheet) params.set('sheet', sheet)
    setPreviewError('')
    void requestJson<Preview>(`/api/files/${selected.file_id}/preview?${params}`).then(
      (data) => { if (active) setPreview(data) },
      (error: Error) => { if (active) setPreviewError(error.message) },
    )
    return () => { active = false }
  }, [canRead, isMarkdown, requestJson, selected, sheet, start])

  /** 切换选中文件并重置行号。Args: file 为待预览的文件。 */
  function open(file: ChatFile) {
    if (selected?.file_id === file.file_id) return
    setPreview(null)
    setStarts([1])
    setSheet('')
    setSelected(file)
  }

  /** 上传文件并回到列表首页。Args: files 为用户选择的原件。 */
  async function upload(files: File[]) {
    if (!files.length || uploading) return
    setActionError('')
    setUploading(true)
    const errors: string[] = []
    const headers = withAuthHeaders()
    let latest: ChatFile | null = null
    try {
      for (const file of files) {
        try {
          latest = await uploadChatFile(file, headers)
        } catch (error) {
          errors.push(file.name + '：' + (error instanceof Error ? error.message : '上传失败'))
        }
      }
      if (latest) {
        setFavorites(false)
        setOffset(0)
        setRefresh((value) => value + 1)
        open(latest)
      }
      setActionError(errors.join('；'))
    } finally {
      setUploading(false)
    }
  }

  /** 切换文件区域并重置预览。Args: showFavorites 表示是否查看收藏。 */
  function selectCollection(showFavorites: boolean) {
    if (showFavorites === favorites) return
    setFavorites(showFavorites)
    setOffset(0)
    setPage(null)
    setSelected(null)
    setPreview(null)
    setPreviewError('')
    setActionError('')
  }

  /** 在全部与收藏之间移动选中文件。Args: file 为目标文件。 */
  async function move(file: ChatFile) {
    setMoving(true)
    setActionError('')
    try {
      await requestJson<ChatFile>(`/api/files/${file.file_id}/favorite`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ favorite: !file.favorite }),
      })
      setSelected((current) => current?.file_id === file.file_id ? null : current)
      setOffset(0)
      setRefresh((value) => value + 1)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '移动文件失败。')
    } finally {
      setMoving(false)
    }
  }

  /** 保存账号的文件保留期。Args: days 为空时关闭自动清理。 */
  async function saveRetention(days: number | null) {
    setSavingRetention(true)
    setActionError('')
    try {
      const saved = await requestJson<Retention>('/api/files/retention', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ retention_days: days }),
      })
      setRetention(saved)
      setRetentionDraft(saved.retention_days?.toString() ?? '')
      setSettingsOpen(false)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '保存清理设置失败。')
    } finally {
      setSavingRetention(false)
    }
  }

  /** 通过认证请求下载选中的文件。Args: file 为待下载的原件。 */
  async function download(file: ChatFile) {
    setActionError('')
    try {
      await downloadChatFile(file.download_url, withAuthHeaders())
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '下载失败。')
    }
  }

  return <section className={styles.page}>
    <header className={styles.header}>
      <div>
        <h1>文件知识库</h1>
        <p>查看上传的文档、聊天附件和模型生成的文件</p>
      </div>
      {canRead && canWrite && <>
        <input ref={input} type="file" hidden multiple accept={CHAT_FILE_TYPES} onChange={(event) => {
          void upload(Array.from(event.currentTarget.files ?? []))
          event.currentTarget.value = ''
        }} />
        <button type="button" className={styles.primary} disabled={uploading} onClick={() => input.current?.click()}>
          {uploading ? '正在上传…' : '上传文件'}
        </button>
      </>}
    </header>
    {!canRead ? <p className={styles.empty}>{isGuest ? '登录后可使用文件知识库。' : '当前账号没有读取文件的权限。'}</p> : <>
      {actionError && <p className={styles.error} role="alert">{actionError}</p>}
      <div className={styles.toolbar}>
        <div className={styles.collections} role="group" aria-label="文件区域">
          <button type="button" aria-pressed={!favorites} onClick={() => selectCollection(false)}>全部</button>
          <button type="button" aria-pressed={favorites} onClick={() => selectCollection(true)}>收藏</button>
        </div>
        <button type="button" className={styles.settingsButton} disabled={!retention}
          aria-expanded={settingsOpen} onClick={() => setSettingsOpen(!settingsOpen)}>
          {retention?.retention_days ? `自动清理 · 保留 ${retention.retention_days} 天` : '自动清理设置'}
        </button>
      </div>
      {settingsOpen && <form className={styles.retention} onSubmit={(event) => {
        event.preventDefault()
        if (canWrite) void saveRetention(Number(retentionDraft))
      }}>
        <p>到期的未收藏文件会自动删除，收藏保留。当前{retention?.retention_days ? '已开启' : '已关闭'}。</p>
        {canWrite && <div>
          <label>保留天数 <input type="number" min={1} max={3650} required value={retentionDraft}
            disabled={savingRetention} onChange={(event) => setRetentionDraft(event.target.value)} /></label>
          <button type="submit" disabled={savingRetention}>保存并启用</button>
          {retention?.retention_days && <button type="button" disabled={savingRetention} onClick={() => void saveRetention(null)}>关闭清理</button>}
        </div>}
      </form>}
      <div className={styles.workspace}>
        <section className={styles.files} aria-label="文件列表">
          <h2>{favorites ? '已收藏文件' : '未收藏文件'}</h2>
          {listError ? <p className={styles.error} role="alert">{listError}</p> :
            !page ? <p className={styles.empty} role="status">正在加载文件…</p> :
            page.files.length === 0 ? <p className={styles.empty}>{favorites ? '还没有收藏文件。' : '这里还没有未收藏的文件。'}</p> :
            <ul>
              {page.files.map((file) => (
                <li key={file.file_id}>
                  <button type="button" className={styles.fileRow} aria-pressed={selected?.file_id === file.file_id}
                    onClick={() => open(file)}>
                    <span className={styles.extension}>{file.extension.slice(1).toUpperCase()}</span>
                    <span className={styles.fileDetails}>
                      <strong title={file.name}>{file.name}</strong>
                      <small>{file.size < 1024 ? file.size + ' B' : (file.size / 1024).toFixed(1) + ' KB'}　{formatDateTime(file.created_at)}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>}
          {(offset > 0 || page?.next_offset != null) && <div className={styles.controls}>
            <button type="button" disabled={offset === 0 || !page} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button>
            <button type="button" disabled={page?.next_offset == null} onClick={() => setOffset(page?.next_offset ?? offset)}>下一页</button>
          </div>}
        </section>
        <section className={styles.preview} aria-label="文件预览">
          <header className={styles.previewHeader}>
            <h2 title={selected?.name}>{selected?.name ?? '文件预览'}</h2>
            {selected && <div className={styles.fileActions}>
              {canWrite && <button type="button" disabled={moving} onClick={() => void move(selected)}>
                {selected.favorite ? '取消收藏' : '移到收藏'}
              </button>}
              <button type="button" onClick={() => void download(selected)}>下载原件</button>
            </div>}
          </header>
          {selected && !isMarkdown && preview?.sheets && <label className={styles.sheet}>
            工作表
            <select value={sheet || preview.sheet || ''} onChange={(event) => {
              setSheet(event.target.value)
              setStarts([1])
            }}>
              {preview.sheets.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
            </select>
          </label>}
          {selected && isMarkdown ? <FileMarkdownPreview key={selected.file_id} path={selected.download_url}
            withAuthHeaders={withAuthHeaders} /> :
            previewError ? <p className={styles.error} role="alert">{previewError}</p> :
            !selected ? <p className={styles.empty}>选择左侧文件查看内容。</p> :
            !preview || preview.sheet !== (sheet || preview.sheet) || (preview.lines.length > 0 && preview.lines[0].line !== start)
              ? <p className={styles.empty} role="status">正在加载预览…</p> :
            <>
              {!!preview.pages_without_text?.length && <p className={styles.note}>无文本层的页码：{preview.pages_without_text.join('、')}</p>}
              {preview.lines.length ? <ol className={styles.lines}>
                {preview.lines.map((line) => <li key={line.line}>
                  <span className={styles.lineNumber} aria-label={'第 ' + line.line + ' 行'}>{line.line}</span>
                  {line.page && <span className={styles.pageNumber}>第 {line.page} 页</span>}
                  <span className={styles.lineText}>
                    {line.cells ? Object.entries(line.cells).map(([column, cell]) => (
                      <span className={styles.cell} key={column}><span>{column}</span> {String(cell.value ?? cell.formula ?? '')}</span>
                    )) : line.content}
                    {line.truncated && ' …'}
                  </span>
                </li>)}
              </ol> : <p className={styles.empty}>此处没有可预览的文本。</p>}
              {(starts.length > 1 || preview.next_start_line !== null) && <div className={styles.controls}>
                <button type="button" disabled={starts.length === 1} onClick={() => setStarts(starts.slice(0, -1))}>上一段</button>
                <span>共 {preview.total_lines} 行</span>
                <button type="button" disabled={preview.next_start_line === null}
                  onClick={() => { if (preview.next_start_line !== null) setStarts([...starts, preview.next_start_line]) }}>下一段</button>
              </div>}
            </>}
        </section>
      </div>
    </>}
  </section>
}
