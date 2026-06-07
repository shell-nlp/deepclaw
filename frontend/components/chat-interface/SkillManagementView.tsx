'use client'

import type { ChangeEvent, Ref } from 'react'

import styles from '../ChatInterface.module.css'
import type { SkillRecord } from './types'
import { formatDateTime } from './utils'

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
  return (
    <div className={styles.managementWorkspace}>
      <section className={styles.managementHero}>
        <div className={styles.managementHeroCopy}>
          <span className={styles.managementHeroEyebrow}>Skill Management</span>
          <h2>上传、查看和删除工作区技能</h2>
          <p>
            上传的 zip 包会自动解压到工作区 `skills` 目录。压缩包根目录必须包含
            `SKILL.md`，每个压缩包对应一个技能目录。
          </p>
        </div>
        <div className={styles.managementHeroActions}>
          <button
            className={styles.managementButton}
            disabled={!canManageSkills || uploadingSkills}
            onClick={onOpenUploadDialog}
          >
            {uploadingSkills ? '上传中...' : '上传技能 zip'}
          </button>
          <input
            ref={uploadInputRef}
            className={styles.hiddenUpload}
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => void onUploadSkills(event)}
          />
        </div>
      </section>

      <div className={styles.managementNoticeRow}>
        {!canManageSkills ? (
          <div className={styles.managementNotice}>{disabledMessage}</div>
        ) : null}
        {skillNotice ? <div className={styles.managementNotice}>{skillNotice}</div> : null}
        {skillError ? <div className={styles.managementError}>{skillError}</div> : null}
      </div>

      <div className={styles.managementSummaryGrid}>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>技能总数</span>
          <strong className={styles.managementSummaryValue}>{total}</strong>
          <span className={styles.managementMeta}>当前工作区已安装的技能目录数量</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>存放位置</span>
          <strong className={styles.managementSummaryValue}>skills</strong>
          <span className={styles.managementMeta}>位于 `.langchain_api/workspace/skills`</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>上传格式</span>
          <strong className={styles.managementSummaryValue}>zip</strong>
          <span className={styles.managementMeta}>根目录必须包含 `SKILL.md`</span>
        </div>
        <div className={styles.managementSummaryCard}>
          <span className={styles.managementSummaryLabel}>加载状态</span>
          <strong className={styles.managementSummaryValue}>
            {loadingSkills ? '刷新中' : '已就绪'}
          </strong>
          <span className={styles.managementMeta}>技能目录变化后会自动刷新列表</span>
        </div>
      </div>

      <section className={styles.managementCard}>
        <div className={styles.managementHeader}>
          <h3>技能列表</h3>
          <span className={styles.managementMeta}>
            {loadingSkills ? '加载中...' : `共 ${total} 个技能`}
          </span>
        </div>
        <div className={styles.managementCardGrid}>
          {skills.length === 0 ? (
            <div className={styles.managementEmpty}>当前工作区还没有已安装技能。</div>
          ) : (
            skills.map((skill) => (
              <div key={skill.skill_name} className={styles.managementTileCard}>
                <div className={styles.managementListHeader}>
                  <strong>{skill.skill_name}</strong>
                  <span>{skill.file_count} 个文件</span>
                </div>
                <p className={styles.managementDescription}>
                  {skill.description || '该技能没有可预览的描述。'}
                </p>
                <div className={styles.managementMetaPanel}>
                  <span>目录: {skill.path}</span>
                  <span>创建时间: {formatDateTime(skill.created_at)}</span>
                  <span>更新时间: {formatDateTime(skill.updated_at)}</span>
                </div>
                <div className={styles.managementActionRow}>
                  <button
                    className={styles.managementDangerMinorButton}
                    disabled={!canManageSkills}
                    onClick={() => void onDeleteSkill(skill.skill_name)}
                  >
                    删除技能
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
