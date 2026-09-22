import type React from 'react'

import styles from '../../ChatInterface.module.css'

export type SidebarIconName =
  | 'chat'
  | 'knowledge'
  | 'skills'
  | 'mcp'
  | 'channels'
  | 'users'

/**
 * 渲染侧边栏导航图标。
 *
 * Args:
 *   name: 图标名称。
 */
export function SidebarIcon({ name }: { name: SidebarIconName }) {
  const paths: Record<SidebarIconName, React.ReactNode> = {
    chat: (
      <>
        <path d="M5.5 6.5h13v8.8h-8.1L7 18.8v-3.5H5.5z" />
        <path d="M8.8 10h6.4M8.8 12.8h4.2" />
      </>
    ),
    knowledge: (
      <>
        <path d="M5.5 5.8h5.1c1.1 0 2 .9 2 2v10.7c0-1.1-.9-2-2-2H5.5z" />
        <path d="M18.5 5.8h-5.1c-1.1 0-2 .9-2 2v10.7c0-1.1.9-2 2-2h5.1z" />
      </>
    ),
    skills: (
      <>
        <path d="m12 4.5 1.7 4.1 4.3 1.7-4.3 1.7-1.7 4.1-1.7-4.1-4.3-1.7 4.3-1.7z" />
        <path d="m18.2 15.7.7 1.7 1.7.7-1.7.7-.7 1.7-.7-1.7-1.7-.7 1.7-.7z" />
      </>
    ),
    mcp: (
      <>
        <circle cx="6.5" cy="12" r="2" />
        <circle cx="17.5" cy="6.5" r="2" />
        <circle cx="17.5" cy="17.5" r="2" />
        <path d="m8.4 11.2 7.2-3.7M8.4 12.8l7.2 3.7" />
      </>
    ),
    channels: (
      <>
        <circle cx="12" cy="6" r="2.2" />
        <circle cx="6" cy="17" r="2.2" />
        <circle cx="18" cy="17" r="2.2" />
        <path d="m10.4 7.9-3 6.8M13.6 7.9l3 6.8M8.2 17h7.6" />
      </>
    ),
    users: (
      <>
        <circle cx="12" cy="8" r="3" />
        <path d="M5.8 19c.8-3.1 3-4.7 6.2-4.7s5.4 1.6 6.2 4.7" />
      </>
    ),
  }

  return (
    <svg
      aria-hidden="true"
      className={styles.sidebarButtonIcon}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  )
}

/**
 * 渲染 DeepClaw 品牌标记。
 *
 * Args:
 *   无。
 */
export function DeepClawMark() {
  return (
    <svg
      aria-hidden="true"
      className={styles.logoGlyph}
      fill="none"
      viewBox="0 0 32 32"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
    >
      <circle cx="16" cy="16" r="10.5" />
      <path d="M6.8 18.4c3.1-2.9 6.2-3.8 9.2-2.7 3 1.1 5.9.4 8.7-2.1" />
      <path d="M9.5 22c2.2-1.7 4.3-2.2 6.3-1.5 2 .7 3.9.3 5.7-1.1" />
      <path d="M13.4 7.3c.6 1.9.3 3.5-.9 4.8" />
    </svg>
  )
}
