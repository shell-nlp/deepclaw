export type Capability = 'files.read' | 'files.write' | 'command.run'
export type Operation = 'list_files' | 'read_file' | 'write_file' | 'run_command'
export type TaskStatus = 'awaiting_approval' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'rejected' | 'uncertain'
export interface Policy { enabled: boolean; revision: number; capabilities: Capability[]; roots: string[] }
export interface ExecuteTask { type: 'execute'; task_id: string; revision: number; operation: Operation; arguments: Record<string, unknown>; expires_at: number }
export interface TaskEvent { type: 'task_event'; task_id: string; sequence: number; status: TaskStatus; output: string; result: Record<string, unknown> | null }
export interface LocalTask extends ExecuteTask { status: TaskStatus; output: string; result: Record<string, unknown> | null }
export interface DesktopState {
  server: string; name: string; paired: boolean; connected: boolean; policy: Policy; tasks: LocalTask[]; error: string
}
export interface DesktopBridge {
  state(): Promise<DesktopState>
  pair(server: string, code: string, name: string): Promise<void>
  policy(change: { enabled?: boolean; allowWrite?: boolean; allowCommand?: boolean }): Promise<void>
  addRoot(): Promise<void>
  removeRoot(root: string): Promise<void>
  decide(taskId: string, approve: boolean): Promise<void>
  cancel(taskId: string): Promise<void>
  unpair(): Promise<void>
  subscribe(listener: (state: DesktopState) => void): () => void
}
