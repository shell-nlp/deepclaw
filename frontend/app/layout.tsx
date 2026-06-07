import type { Metadata } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'DeepClaw',
  description: 'DeepClaw 智能体工作台，支持工具调用、知识库与流式响应',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
