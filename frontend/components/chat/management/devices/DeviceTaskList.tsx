import type { ClientDeviceTask } from '../../hooks/useDevices'
import styles from './Devices.module.css'
const operations: Record<string, string> = { list_files: '浏览目录', read_file: '读取文件', write_file: '写入文件', run_command: '运行命令' }
const statuses: Record<string, string> = { pending: '等待设备接收', queued: '等待自动执行', awaiting_approval: '等待本机确认', running: '执行中', succeeded: '已完成', failed: '执行失败', rejected: '本机已拒绝', cancelled: '已取消', uncertain: '需要核对' }

/** 展示设备真实执行记录，取消后等待本机回执；Args: tasks 任务, busy 提交标识, onCancel 取消请求。 */
export function DeviceTaskList({ tasks, busy, onCancel }: { tasks: ClientDeviceTask[]; busy: string; onCancel: (id: string) => void }) {
  return <section className={styles.tasks}><div className={styles.sectionHeading}><h3>最近执行</h3><span>{tasks.length} 条记录</span></div>{!tasks.length ? <div className={styles.emptyTasks}><p>还没有本机任务</p><span>在聊天输入框中选择设备后，即可让智能体使用已授权的能力。</span></div> : tasks.map(task => <article className={styles.task} key={task.id}><div className={styles.taskTitle}><strong>{operations[task.operation] || task.operation}</strong><span>{task.cancel_requested && !['succeeded', 'failed', 'rejected', 'cancelled', 'uncertain'].includes(task.status) ? '正在请求停止' : statuses[task.status] || task.status}</span></div><p className={styles.taskTarget}>{String(task.arguments.path || task.arguments.cwd || '')}</p><details><summary>查看参数和结果</summary><pre>{JSON.stringify(task.arguments, null, 2)}</pre>{task.output && <pre>{task.output}</pre>}{task.result && <pre>{JSON.stringify(task.result, null, 2)}</pre>}</details>{['pending', 'queued', 'awaiting_approval', 'running'].includes(task.status) && <button className={styles.textButton} disabled={!!busy || task.cancel_requested} onClick={() => onCancel(task.id)}>停止任务</button>}</article>)}</section>
}
