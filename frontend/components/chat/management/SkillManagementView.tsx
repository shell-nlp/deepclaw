'use client'

import { useState, type ChangeEvent, type Ref } from 'react'

import styles from '../../ChatInterface.module.css'
import type { SkillRecord } from '../../chat-interface/types'
import { formatDateTime } from '../../chat-interface/utils'

interface SkillManagementViewProps {
  skills: SkillRecord[]
  total: number
  uploadingSkills: boolean
  loadingSkills: boolean
  skillNotice: string
  skillError: string
  canManageSkills: boolean
  disabledMessage: string
  uploadInputRef: Ref<HTMLInputElement>
  onOpenUploadDialog: () => void
  onUploadSkills: (event: ChangeEvent<HTMLInputElement>) => void | Promise<void>
  onDeleteSkill: (skillName: string) => void | Promise<void>
}

export function SkillManagementView({
  skills,
  total,
  uploadingSkills,
  loadingSkills,
  skillNotice,
  skillError,
  canManageSkills,
  disabledMessage,
  uploadInputRef,
  onOpenUploadDialog,
  onUploadSkills,
  onDeleteSkill,
}: SkillManagementViewProps) {
  const [search, setSearch] = useState('')
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)
  const visibleSkills = skills.filter((skill) =>
    `${skill.skill_name} ${skill.description}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
  )

  return (
    <div className={`${styles.managementWorkspace} ${styles.extensionWorkspace}`}>
      <header className={styles.extensionHeading}>
        <div>
          <span className={styles.extensionEyebrow}>EXTENSIONS / SKILLS</span>
          <h2>技能管理</h2>
          <p>查看和管理当前工作区的技能。</p>
        </div>
        <div className={styles.extensionHeadingActions}>
          <span className={styles.extensionCount}>{total} 个技能</span>
          <button
            className={styles.extensionPrimaryButton}
            disabled={!canManageSkills || uploadingSkills}
            onClick={onOpenUploadDialog}
          >
            <span aria-hidden="true">＋</span> {uploadingSkills ? '上传中…' : '上传技能'}
          </button>
          <input
            ref={uploadInputRef}
            className={styles.hiddenUpload}
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => void onUploadSkills(event)}
          />
        </div>
      </header>

      {(!canManageSkills || skillNotice || skillError) && (
        <div role={skillError ? 'alert' : 'status'} className={skillError ? styles.managementError : styles.managementNotice}>
          {skillError || (!canManageSkills ? disabledMessage : skillNotice)}
        </div>
      )}

      <div className={styles.extensionSectionHeading}>
        <div>
          <div className={styles.extensionSectionLabel}>已安装的技能 <span>{total}</span></div>
          <p>技能包为 ZIP 格式，根目录需包含 SKILL.md。</p>
        </div>
        <label className={styles.extensionSearch}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索技能" aria-label="搜索技能" />
        </label>
      </div>

      <div className={styles.extensionList} aria-busy={loadingSkills}>
        {visibleSkills.length === 0 ? (
          <div className={styles.extensionEmpty}>
            <strong>{loadingSkills ? '正在加载技能…' : search ? '没有匹配的技能' : '还没有安装技能'}</strong>
            <span>{search ? '试试其他名称或描述。' : '上传包含 SKILL.md 的 ZIP 包即可安装。'}</span>
          </div>
        ) : visibleSkills.map((skill) => (
          <div className={styles.extensionListEntry} key={skill.skill_name}>
            <div className={styles.extensionListRow}>
              <button
                className={styles.extensionSkillExpand}
                onClick={() => setExpandedSkill(expandedSkill === skill.skill_name ? null : skill.skill_name)}
                aria-expanded={expandedSkill === skill.skill_name}
                aria-label={`${expandedSkill === skill.skill_name ? '收起' : '展开'} ${skill.skill_name} 详情`}
              >
                <span className={`${styles.extensionChevron} ${expandedSkill === skill.skill_name ? styles.extensionChevronOpen : ''}`} aria-hidden="true">⌄</span>
                <span className={styles.extensionSkillIcon} aria-hidden="true">{skill.skill_name.slice(0, 1).toUpperCase()}</span>
                <span className={styles.extensionRowMain}>
                  <strong>{skill.skill_name}</strong>
                  <small>{skill.description || '暂无技能描述'}</small>
                </span>
              </button>
              <span className={styles.extensionTransport}>{skill.file_count} 个文件</span>
              <button
                className={styles.extensionDeleteButton}
                disabled={!canManageSkills}
                title={`删除 ${skill.skill_name}`}
                onClick={() => void onDeleteSkill(skill.skill_name)}
              >删除</button>
            </div>
            {expandedSkill === skill.skill_name && (
              <div className={styles.extensionRowDetail}>
                <div><span>存放目录</span><code title={skill.path}>{skill.path}</code></div>
                <div><span>创建时间</span><strong>{formatDateTime(skill.created_at)}</strong></div>
                <div><span>最近更新</span><strong>{formatDateTime(skill.updated_at)}</strong></div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
