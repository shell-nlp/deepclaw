import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from deepclaw.common.object_storage import create_object_storage
from deepclaw.middleware.cron.executor import BUCKET, MIME_TYPES, artifact_key
from deepclaw.middleware.cron.schedule_store import get_schedule_store
from deepclaw.middleware.cron.schemas import NotificationsResponse, ScheduleRequest, ScheduleResponse
from deepclaw.settings import settings
from deepclaw.web_backend.auth.dependencies import CurrentActor
from deepclaw.web_backend.auth.rbac.dependencies import require_permission

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class MarkReadRequest(BaseModel):
    ids: list[str] = Field(max_length=50)


class ScheduleEnabledRequest(BaseModel):
    enabled: bool


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(actor: CurrentActor = Depends(require_permission("/api/schedules", "read"))):
    """列出本人定时任务。

    Args:
        actor: 已认证用户。
    """
    return await get_schedule_store().list_jobs(actor.user_id)


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(body: ScheduleRequest, actor: CurrentActor = Depends(require_permission("/api/schedules", "write"))):
    """创建定时任务。

    Args:
        body: 任务设置。
        actor: 已认证用户。
    """
    try:
        return await get_schedule_store().save(actor.user_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/{job_id}", response_model=ScheduleResponse)
async def update_schedule(job_id: str, body: ScheduleRequest, actor: CurrentActor = Depends(require_permission("/api/schedules", "write"))):
    """保存本人任务的设置。

    Args:
        job_id: 任务 ID。
        body: 完整任务设置。
        actor: 已认证用户。
    """
    try:
        return await get_schedule_store().save(actor.user_id, body, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{job_id}", status_code=204)
async def delete_schedule(job_id: str, actor: CurrentActor = Depends(require_permission("/api/schedules", "write"))):
    """删除本人任务。

    Args:
        job_id: 任务 ID。
        actor: 已认证用户。
    """
    try:
        await get_schedule_store().remove(actor.user_id, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{job_id}/enabled", response_model=ScheduleResponse)
async def set_schedule_enabled(
    job_id: str, body: ScheduleEnabledRequest,
    actor: CurrentActor = Depends(require_permission("/api/schedules", "write")),
):
    """暂停或启动本人任务。

    Args:
        job_id: 任务 ID。
        body: 目标启停状态。
        actor: 已认证用户。
    """
    try:
        return await get_schedule_store().set_enabled(actor.user_id, job_id, body.enabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/notifications", response_model=NotificationsResponse)
async def get_notifications(
    before: str | None = None, actor: CurrentActor = Depends(require_permission("/api/schedules", "read")),
):
    """获取带执行时间的任务结果。

    Args:
        before: 上一批最后一条结果的 ID。
        actor: 已认证用户。
    """
    return await get_schedule_store().notifications(actor.user_id, before)


@router.post("/notifications/read", status_code=204)
async def mark_notifications_read(body: MarkReadRequest, actor: CurrentActor = Depends(require_permission("/api/schedules", "read"))):
    """标记已查看的任务通知。

    Args:
        body: 要标记的通知 ID。
        actor: 已认证用户。
    """
    await get_schedule_store().mark_read(actor.user_id, body.ids)


@router.get("/notifications/{run_id}/file")
async def download_result(run_id: str, actor: CurrentActor = Depends(require_permission("/api/schedules", "read"))):
    """下载本人任务产物。

    Args:
        run_id: 任务执行 ID。
        actor: 已认证用户。
    """
    run = await get_schedule_store().artifact(actor.user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="找不到任务文件。")
    extension = run.filename.rsplit(".", 1)[-1]
    try:
        data = await asyncio.to_thread(
            create_object_storage(settings).get_bytes, BUCKET, artifact_key(run, extension),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="找不到任务文件。") from exc
    return Response(data, media_type=MIME_TYPES[extension], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(run.filename, safe='')}",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.delete("/notifications/{run_id}", status_code=204)
async def delete_notification(run_id: str, actor: CurrentActor = Depends(require_permission("/api/schedules", "write"))):
    """删除本人已完成的任务通知和关联文件。

    Args:
        run_id: 任务执行 ID。
        actor: 已认证用户。
    """
    store = get_schedule_store()
    run = await store.artifact(actor.user_id, run_id)
    if run is not None:
        extension = run.filename.rsplit(".", 1)[-1]
        await asyncio.to_thread(
            create_object_storage(settings).delete_object, BUCKET, artifact_key(run, extension)
        )
    try:
        await store.delete_notification(actor.user_id, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

