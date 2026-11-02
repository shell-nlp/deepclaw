import { copyFile, mkdir, rename } from 'node:fs/promises'
import { readFileSync } from 'node:fs'

// 将当前版本安装包原子发布到服务端固定下载目录，避免用户下载构建中的文件。
const desktopRoot = new URL('../', import.meta.url)
const { version } = JSON.parse(readFileSync(new URL('package.json', desktopRoot), 'utf8'))
const source = new URL(`release/DeepClaw 本机助手 Setup ${version}.exe`, desktopRoot)
const target = new URL('../.deepclaw/downloads/', desktopRoot)
await mkdir(target, { recursive: true })
await copyFile(source, new URL('DeepClaw-Setup-x64.exe.tmp', target))
await rename(new URL('DeepClaw-Setup-x64.exe.tmp', target), new URL('DeepClaw-Setup-x64.exe', target))
console.log('Windows 安装包已发布至 .deepclaw/downloads/DeepClaw-Setup-x64.exe')
