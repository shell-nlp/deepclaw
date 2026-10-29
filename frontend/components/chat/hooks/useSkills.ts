'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'

import {
  SKILL_DELETE_API_PATH,
  SKILL_LIST_API_PATH,
  SKILL_UPLOAD_API_PATH,
} from '../utils/constants'
import type {
  SkillDeleteResponse,
  SkillListResponse,
  SkillRecord,
  SkillUploadResponse,
} from '../utils/types'

type RequestJson = <T>(path: string, init?: RequestInit) => Promise<T>

/**
 * 管理技能列表的加载、上传与删除。
 *
 * Args:
 *   requestJson: 带认证头的接口请求函数。
 */
export function useSkills(requestJson: RequestJson) {
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [loadingSkills, setLoadingSkills] = useState(false)
  const [uploadingSkills, setUploadingSkills] = useState(false)
  const [skillNotice, setSkillNotice] = useState('')
  const [skillError, setSkillError] = useState('')
  const skillUploadInputRef = useRef<HTMLInputElement>(null)

  const loadSkills = useCallback(async () => {
    setLoadingSkills(true)
    setSkillError('')
    try {
      const result = await requestJson<SkillListResponse>(SKILL_LIST_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search: '' }),
      })
      setSkills(result.items)
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '加载技能列表失败。')
      setSkills([])
    } finally {
      setLoadingSkills(false)
    }
  }, [requestJson])

  useEffect(() => {
    void loadSkills()
  }, [loadSkills])

  const openSkillUploadDialog = () => {
    skillUploadInputRef.current?.click()
  }

  const handleUploadSkill = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setUploadingSkills(true)
    setSkillNotice('')
    setSkillError('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const result = await requestJson<SkillUploadResponse>(SKILL_UPLOAD_API_PATH, {
        method: 'POST',
        body: formData,
      })
      await loadSkills()
      setSkillNotice(
        `技能 "${result.skill.skill_name}" 上传完成，共解压 ${result.extracted_files} 个文件。`
      )
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '上传技能失败。')
    } finally {
      setUploadingSkills(false)
      event.target.value = ''
    }
  }

  const deleteSkill = async (skillName: string) => {
    if (!window.confirm(`确认删除技能 "${skillName}" 吗？`)) return

    setSkillNotice('')
    setSkillError('')
    try {
      const result = await requestJson<SkillDeleteResponse>(SKILL_DELETE_API_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: skillName }),
      })
      await loadSkills()
      setSkillNotice(`技能 "${result.skill_name}" 已删除。`)
    } catch (error) {
      setSkillError(error instanceof Error ? error.message : '删除技能失败。')
    }
  }

  return {
    skills,
    loadingSkills,
    uploadingSkills,
    skillNotice,
    skillError,
    skillUploadInputRef,
    loadSkills,
    openSkillUploadDialog,
    handleUploadSkill,
    deleteSkill,
  }
}
