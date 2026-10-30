"""渠道任务状态与安全补发接口，禁止通过重试重新执行 Agent。"""

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from deepclaw.web_backend.auth.dependencies import CurrentActor, get_current_actor
from deepclaw.web_backend.channels.common import is_admin, manager_user_id_from_actor
from deepclaw.web_backend.channels.jobs import ChannelJob, ChannelJobStore
from deepclaw.web_backend.channels.store import ChannelStore, get_channel_store


class ChannelJobResponse(BaseModel):
    """不含正文、凭据和原始消息的渠道任务状态。"""

    id: str
    channel: str
    binding_id: int | None
    message_id: str
    execution_status: str
    delivery_status: str
    attempts: int
    error: str | None


class ChannelJobListResponse(BaseModel):
    """当前可见的未完成渠道任务。"""

    items: list[ChannelJobResponse]


class ChannelJobActionRequest(BaseModel):
    """只补发或人工结束任务的操作请求。"""

    action: Literal["retry_delivery", "close"]


def job_response(job):
    """只序列化允许展示的任务字段。

    Args:
        job: 持久化任务。
    """
    return ChannelJobResponse(id=job.id, channel=job.payload["channel"], binding_id=job.payload.get("binding_id"),
                              message_id=job.payload["message_id"], execution_status=job.execution_status,
                              delivery_status=job.delivery_status, attempts=job.attempts, error=job.error)


router = APIRouter(tags=["channels"])


@router.get("/jobs", response_model=ChannelJobListResponse)
async def list_jobs(scope: Literal["my", "all"] = "my", actor: CurrentActor = Depends(get_current_actor),
                    store: ChannelStore = Depends(get_channel_store)):
    """查询未完成任务，管理员可查看全部。

    Args:
        scope: 当前用户或管理员范围。
        actor: 当前身份。
        store: 渠道存储。
    """
    if scope == "all" and not is_admin(actor):
        raise HTTPException(403, "只有管理员可以查看全部渠道任务")
    await store._ensure_init()
    statement = select(ChannelJob).where(ChannelJob.delivery_status != "delivered")
    if scope != "all":
        user_id = manager_user_id_from_actor(actor)
        statement = statement.where((ChannelJob.owner_user_id == user_id) | (ChannelJob.manager_user_id == user_id))
    async with store.async_session() as session:
        jobs = (await session.exec(statement.order_by(ChannelJob.created_at).limit(100))).all()
        return ChannelJobListResponse(items=[job_response(job) for job in jobs])


@router.post("/jobs/{job_id}/actions", response_model=ChannelJobResponse)
async def job_action(job_id: str, request: ChannelJobActionRequest,
                     actor: CurrentActor = Depends(get_current_actor), store: ChannelStore = Depends(get_channel_store)):
    """补发已有结果或在人工核对后结束异常任务，不创建 Run。

    Args:
        job_id: 任务主键。
        request: 补发或结束操作。
        actor: 当前身份。
        store: 渠道存储。
    """
    await store._ensure_init()
    async with store.async_session() as session:
        job = await session.get(ChannelJob, job_id)
    user_id = manager_user_id_from_actor(actor)
    if job is None or (not is_admin(actor) and user_id not in {job.owner_user_id, job.manager_user_id}):
        raise HTTPException(404, "渠道任务不存在")
    jobs = ChannelJobStore(store)
    async with jobs.lease(f"session:{job.session_key}") as acquired:
        if not acquired:
            raise HTTPException(409, "该会话正在处理中，请稍后操作")
        job = await jobs.get(job_id)
        if request.action == "retry_delivery":
            if job.execution_status not in {"completed", "interrupted"} or job.delivery_status not in {"failed", "pending"}:
                raise HTTPException(409, "仅支持补发已完成且投递结果明确的回复")
            job.delivery_status = "pending"
            job.next_attempt_at = 0
        else:
            if not job.error and job.delivery_status != "uncertain":
                raise HTTPException(409, "只能结束需要核对的异常任务")
            job.execution_status = "failed"
            job.delivery_status = "delivered"
            job.resolved_by, job.resolved_at = user_id, time.time()
            job.error = None
        await jobs.save(job)
        return job_response(job)
