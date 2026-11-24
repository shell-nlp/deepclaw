import json
from typing import Annotated, Literal

from langchain.tools import ToolRuntime, tool
from pydantic import ValidationError

from deepclaw.middleware.cron.schedule_store import get_schedule_store
from deepclaw.middleware.cron.schemas import ScheduleRequest
from deepclaw.web_backend.auth.rbac.dependencies import agent_has_permission


@tool
async def cron_tool(
    runtime: ToolRuntime,
    action: Annotated[Literal["add", "list", "update", "remove"], "新增、查询、修改或删除定时任务"],
    job_id: Annotated[str | None, "修改或删除时，从查询结果取得的任务 ID"] = None,
    changes: Annotated[dict | None, "新增时填写任务设置，修改时仅填写需要更改的设置"] = None,
) -> str:
    """管理当前登录账号的定时任务，与网页任务管理共用数据。

    新建需提供 name（名称）和 content（提醒正文或生成要求）。
    一次性任务提供带时区偏移的 ISO 8601 run_at，例如 2026-11-25T09:00:00+08:00。
    固定间隔使用 interval_seconds，例如每 10 秒执行一次填写 10。
    日历周期使用五段 cron（分 时 日 月 周）或六段 cron（秒 分 时 日 月 周），
    例如 */10 * * * * * 表示每分钟的第 0、10、20、30、40、50 秒执行。
    IANA timezone 默认 Asia/Shanghai。修改触发类型时把旧的触发字段设为 null。
    mode 可选 literal（原样交付，默认）或 generate（调用模型生成正文）。
    output 可选 notification（铃铛文字提醒，默认）、md 或 docx（铃铛中下载）。
    enabled 可启用或暂停任务。删除和修改前用 list 确认任务 ID。时间有歧义时先询问用户。

    Args:
        runtime: 框架注入的认证运行时。
        action: 要执行的任务操作。
        job_id: 目标任务 ID。
        changes: 任务配置或要修改的字段。
    """
    principal = runtime.config.get("configurable", {}).get("langgraph_auth_user")
    owner = getattr(principal, "identity", None)
    if not owner or owner == "guest":
        return "请登录后使用定时任务。"
    permission = "read" if action == "list" else "write"
    if not await agent_has_permission(owner, "/api/schedules", permission):
        return "没有访问定时任务的权限。"
    store = get_schedule_store()
    if action == "list":
        jobs = await store.list_jobs(owner)
        return json.dumps([job.model_dump(mode="json") for job in jobs], ensure_ascii=False)
    if action != "add" and not job_id:
        return "请先查询任务并提供任务 ID。"
    try:
        if action == "remove":
            await store.remove(owner, job_id)
            return "定时任务已删除。"
        values = changes or {}
        if action == "update":
            jobs = await store.list_jobs(owner)
            job = next((job for job in jobs if job.id == job_id), None)
            if job is None:
                return "找不到定时任务。"
            values = {**job.settings.model_dump(mode="json"), **values}
        task = ScheduleRequest.model_validate(values)
        saved = await store.save(owner, task, job_id if action == "update" else None)
    except ValidationError as exc:
        return "任务设置有误：" + "；".join(
            f"{'.'.join(map(str, error['loc']))} {error['msg']}" for error in exc.errors()
        )
    except (LookupError, ValueError) as exc:
        return str(exc)
    return saved.model_dump_json()
