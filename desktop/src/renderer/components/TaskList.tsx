import type { DesktopBridge, LocalTask } from '../../shared/protocol'
const names = { list_files: '浏览目录', read_file: '读取文件', write_file: '写入文件', run_command: '运行命令' }
const statuses = { awaiting_approval: '等待你确认', running: '正在执行', succeeded: '已完成', failed: '执行失败', cancelled: '已取消', rejected: '已拒绝', uncertain: '需要核对' }

/** 渲染真实本机任务、完整审批参数和执行输出；Args: tasks 任务列表, busy 提交状态, act 本机操作入口。 */
export function TaskList({ tasks, busy, act }: { tasks: LocalTask[]; busy: boolean; act: (action: (bridge: DesktopBridge) => Promise<void>) => Promise<void> }) {
  return <section className="task-panel" id="execution-records"><div className="section-heading"><div><h3>执行记录</h3><p>每一次本机操作，都有据可查。</p></div><span className="count">{tasks.length} 条</span></div>
    {!tasks.length ? <div className="empty-tasks"><span className="empty-line"/><p>还没有执行任务</p><small>在聊天中选择这台设备后，任务会显示在这里。</small></div> : tasks.map(task => <article className="task" key={task.task_id} data-status={task.status}>
      <div className="task-title"><strong>{names[task.operation]}</strong><span>{statuses[task.status]}</span></div>
      <p className="task-target" title={String(task.arguments.path || task.arguments.cwd || '')}>{String(task.arguments.path || task.arguments.cwd || '')}</p>
      {task.status === 'awaiting_approval' && <><pre className="task-arguments">{JSON.stringify(task.arguments, null, 2)}</pre><div className="task-actions"><button className="secondary" disabled={busy} onClick={() => void act(bridge => bridge.decide(task.task_id, false))}>拒绝</button><button className="primary" disabled={busy} onClick={() => void act(bridge => bridge.decide(task.task_id, true))}>允许此次操作</button></div></>}
      {task.status === 'running' && <button className="text-button danger" disabled={busy} onClick={() => void act(bridge => bridge.cancel(task.task_id))}>停止任务</button>}
      {(task.output || task.result) && <details><summary>查看结果</summary>{task.output && <pre>{task.output}</pre>}{task.result && <pre>{JSON.stringify(task.result, null, 2)}</pre>}</details>}
    </article>)}
  </section>
}
