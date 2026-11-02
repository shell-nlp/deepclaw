import fs from 'node:fs/promises'
import { spawn, type ChildProcess } from 'node:child_process'
import { StringDecoder } from 'node:string_decoder'
import type { ExecuteTask, Policy } from '../shared/protocol'
import { authorizedPath, assertPermission } from './permissions'

/** 执行本机操作；Args: task 已确认任务, policy 即时权限, signal 取消信号, output 输出回调。 */
export async function execute(task: ExecuteTask, policy: () => Policy, signal: AbortSignal, output: (text: string) => void): Promise<Record<string, unknown>> {
  assertPermission(task, policy())
  const args = task.arguments
  const filename = await authorizedPath(task.operation === 'run_command' ? args.cwd : args.path, policy().roots, task.operation === 'write_file')
  // 路径解析后再次检查，防止期间关闭开关或取消。
  assertPermission(task, policy()); signal.throwIfAborted()
  if (task.operation === 'list_files') {
    const entries = await fs.readdir(filename, { withFileTypes: true })
    return { entries: entries.slice(0, 1000).map(entry => ({ name: entry.name, directory: entry.isDirectory(), link: entry.isSymbolicLink() })), truncated: entries.length > 1000 }
  }
  if (task.operation === 'read_file') {
    const handle = await fs.open(filename, 'r')
    try {
      const stat = await handle.stat()
      if (!stat.isFile() || stat.size > 262144) throw new Error('仅支持读取不超过 256 KB 的文本文件')
      const content = await handle.readFile({ encoding: 'utf8' })
      return { content }
    } finally { await handle.close() }
  }
  if (task.operation === 'write_file') {
    if (typeof args.content !== 'string' || Buffer.byteLength(args.content) > 262144) throw new Error('写入内容不能超过 256 KB')
    await fs.writeFile(filename, args.content, { encoding: 'utf8', signal })
    return { message: '文件已写入' }
  }
  if (typeof args.program !== 'string' || !args.program || !Array.isArray(args.argv) || args.argv.some(value => typeof value !== 'string') || args.argv.length > 128) throw new Error('命令参数不合法')
  const timeout = Math.min(300, Math.max(1, Number(args.timeout) || 60))
  return await runCommand(args.program, args.argv, filename, timeout, signal, output)
}

/** 终止进程树；Args: child 受控子进程。 */
export async function killTree(child: ChildProcess): Promise<void> {
  if (!child.pid) return
  if (process.platform === 'win32') {
    await new Promise<void>((resolve) => {
      const killer = spawn('taskkill.exe', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, shell: false })
      killer.once('close', () => resolve()); killer.once('error', () => { child.kill(); resolve() })
    })
  } else {
    try { process.kill(-child.pid, 'SIGKILL') } catch { child.kill('SIGKILL') }
  }
}

/** 有界输出与超时的进程执行；Args: program 程序, argv 参数, cwd 工作目录, timeout 超时秒数, signal 取消信号, output 输出回调。 */
async function runCommand(program: string, argv: string[], cwd: string, timeout: number, signal: AbortSignal, output: (text: string) => void) {
  return await new Promise<Record<string, unknown>>((resolve, reject) => {
    const child = spawn(program, argv, { cwd, shell: false, windowsHide: true, detached: process.platform !== 'win32', stdio: ['ignore', 'pipe', 'pipe'] })
    let bytes = 0, stopped = false
    const stop = () => { stopped = true; void killTree(child) }
    const timer = setTimeout(stop, timeout * 1000)
    signal.addEventListener('abort', stop, { once: true })
    for (const stream of [child.stdout, child.stderr]) {
      const decoder = new StringDecoder('utf8')
      stream?.on('data', (data: Buffer) => {
        if (bytes >= 131072) return
        const remaining = 131072 - bytes; const chunk = data.subarray(0, remaining); bytes += chunk.length
        output(decoder.write(chunk))
      })
      stream?.on('end', () => { const tail = decoder.end(); if (tail) output(tail) })
    }
    child.once('error', () => { clearTimeout(timer); signal.removeEventListener('abort', stop); reject(new Error('程序启动失败，请检查程序是否安装')) })
    child.once('close', (code) => {
      clearTimeout(timer); signal.removeEventListener('abort', stop)
      if (stopped || signal.aborted) reject(new Error('进程已停止或已超时'))
      else resolve({ exit_code: code, output_truncated: bytes >= 131072 })
    })
    if (signal.aborted) stop()
  })
}
