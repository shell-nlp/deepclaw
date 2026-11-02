export type Capability = 'files.read' | 'files.write' | 'command.run'
export type Operation = 'list_files' | 'read_file' | 'write_file' | 'run_command'
export type ApprovalMode = 'confirm' | 'auto'
export type PolicyChange = { enabled?: boolean; allowWrite?: boolean; allowCommand?: boolean; approvalMode?: ApprovalMode }
export type TaskStatus = 'queued' | 'awaiting_approval' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'rejected' | 'uncertain'
export interface Policy { enabled: boolean; revision: number; capabilities: Capability[]; roots: string[]; approvalMode: ApprovalMode }
export interface ExecuteTask { type: 'execute'; task_id: string; revision: number; operation: Operation; arguments: Record<string, unknown>; expires_at: number }
export interface TaskEvent { type: 'task_event'; task_id: string; sequence: number; status: TaskStatus; output: string; result: Record<string, unknown> | null }
export interface LocalTask extends ExecuteTask { status: TaskStatus; output: string; result: Record<string, unknown> | null; approval?: 'automatic' | 'manual' }
export interface DesktopState {
  server: string; name: string; paired: boolean; connected: boolean; policy: Policy; tasks: LocalTask[]; error: string
}
export interface DesktopBridge {
  state(): Promise<DesktopState>
  pair(server: string, code: string, name: string): Promise<void>
  policy(change: PolicyChange): Promise<void>
  addRoot(): Promise<void>
  removeRoot(root: string): Promise<void>
  decide(taskId: string, approve: boolean): Promise<void>
  cancel(taskId: string): Promise<void>
  unpair(): Promise<void>
  updateState(): Promise<DesktopUpdateState>
  checkUpdate(): Promise<void>
  installUpdate(): Promise<void>
  subscribeUpdate(listener: (state: DesktopUpdateState) => void): () => void
  subscribe(listener: (state: DesktopState) => void): () => void
}

export interface DesktopUpdateState {
  currentVersion: string
  status: 'idle' | 'checking' | 'available' | 'downloading' | 'installing' | 'error' | 'unsupported'
  latestVersion?: string
  percent?: number
  lastCheckedAt?: number
  message: string
}
