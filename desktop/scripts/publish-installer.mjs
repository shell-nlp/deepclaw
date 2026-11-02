import { copyFile, mkdir, rename, stat, writeFile } from 'node:fs/promises'
import { readFileSync, createReadStream, existsSync } from 'node:fs'
import { createHash } from 'node:crypto'

// 分发源由客户端在配对后指定；先发布版本文件，最后原子替换清单。
const desktopRoot = new URL('../', import.meta.url)
const { version } = JSON.parse(readFileSync(new URL('package.json', desktopRoot), 'utf8'))
const filename = `DeepClaw-Setup-x64-${version}.exe`
const source = new URL(`release/${filename}`, desktopRoot)
const target = new URL('../.deepclaw/downloads/', desktopRoot)
const updates = new URL('updates/', target)
await mkdir(updates, { recursive: true })
/** 流式计算发布文件摘要，避免将安装包整体加载到内存。
 * Args:
 *   file: 待计算文件的 URL。
 */
async function checksum(file) {
  const hash = createHash('sha512')
  for await (const chunk of createReadStream(file)) hash.update(chunk)
  return hash.digest('base64')
}
const sha512 = await checksum(source)
const size = (await stat(source)).size
if (existsSync(new URL(filename, updates)) && await checksum(new URL(filename, updates)) !== sha512) throw new Error('同一版本不能替换安装包，请递增 desktop/package.json 中的版本后重新打包。')
await copyFile(source, new URL(`${filename}.tmp`, updates))
await rename(new URL(`${filename}.tmp`, updates), new URL(filename, updates))
await copyFile(new URL(`release/${filename}.blockmap`, desktopRoot), new URL(`${filename}.blockmap`, updates))
await copyFile(source, new URL('DeepClaw-Setup-x64.exe.tmp', target))
await rename(new URL('DeepClaw-Setup-x64.exe.tmp', target), new URL('DeepClaw-Setup-x64.exe', target))
// JSON 是 YAML 的兼容子集，直接生成标准 electron-updater 清单。
const manifest = { version, files: [{ url: filename, sha512, size }], path: filename, sha512, releaseDate: new Date().toISOString() }
await writeFile(new URL('latest.yml.tmp', updates), JSON.stringify(manifest, null, 2))
await rename(new URL('latest.yml.tmp', updates), new URL('latest.yml', updates))
console.log(`安装包 ${version} 与更新清单已发布至 .deepclaw/downloads；未上传到外部服务。`)
